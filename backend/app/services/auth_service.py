import re
import uuid
from typing import Optional, Tuple, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.company import Company
from app.models.membership import CompanyMember, MemberRole
from app.models.join_request import WorkspaceJoinRequest, JoinRequestStatus
from app.schemas.auth import OwnerRegisterRequest, LoginRequest
from app.core.security import hash_password, verify_password, create_access_token
from app.services.audit_service import log_audit_event


def slugify(text: str) -> str:
    """Generate a clean URL/identifier-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "workspace"


def register_owner(
    db: Session,
    request: OwnerRegisterRequest,
    ip_address: Optional[str] = None
) -> Tuple[User, Company, str]:
    """
    Transactionally register a new user as OWNER and create their company workspace.
    Fails atomically if the email exists or if an integrity error occurs.
    """
    # Check if email is already in use
    existing_user = db.query(User).filter(User.email == request.email.lower().strip()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # Generate unique slug for company
    base_slug = slugify(request.company_name)
    slug = base_slug
    counter = 1
    while db.query(Company).filter(Company.slug == slug).first():
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        counter += 1
        if counter > 5:
            slug = f"{base_slug}-{uuid.uuid4().hex[:12]}"
            break

    try:
        # Create user
        user = User(
            email=request.email.lower().strip(),
            hashed_password=hash_password(request.password),
            full_name=request.full_name.strip(),
            is_active=True,
        )
        db.add(user)
        db.flush()  # populate user.id

        # Create company
        company = Company(
            name=request.company_name.strip(),
            slug=slug,
        )
        db.add(company)
        db.flush()  # populate company.id

        # Create OWNER membership
        membership = CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role=MemberRole.OWNER,
        )
        db.add(membership)

        # Log audit event
        log_audit_event(
            db=db,
            action="USER_REGISTER_OWNER",
            resource_type="company",
            company_id=company.id,
            user_id=user.id,
            resource_id=company.id,
            details={"company_name": company.name, "email": user.email},
            ip_address=ip_address,
        )

        db.commit()
        db.refresh(user)
        db.refresh(company)

        token = create_access_token(subject=user.id)
        return user, company, token

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the account and workspace."
        )


def authenticate_user(
    db: Session,
    request: LoginRequest,
    ip_address: Optional[str] = None
) -> Tuple[User, str, List[Tuple[Company, MemberRole]]]:
    """Authenticate user credentials and return user, access token, and memberships."""
    user = db.query(User).filter(User.email == request.email.lower().strip()).first()
    if not user or not verify_password(request.password, user.hashed_password):
        log_audit_event(
            db=db,
            action="LOGIN_FAILED",
            resource_type="user",
            details={"email": request.email.lower().strip()},
            ip_address=ip_address,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Please contact your workspace administrator.",
        )

    # Get all company memberships
    memberships = (
        db.query(CompanyMember, Company)
        .join(Company, CompanyMember.company_id == Company.id)
        .filter(CompanyMember.user_id == user.id)
        .all()
    )

    companies_with_roles = [(comp, member.role) for member, comp in memberships]

    if len(companies_with_roles) == 0:
        latest_request = (
            db.query(WorkspaceJoinRequest, Company)
            .join(Company, WorkspaceJoinRequest.company_id == Company.id)
            .filter(WorkspaceJoinRequest.user_id == user.id)
            .order_by(WorkspaceJoinRequest.created_at.desc())
            .first()
        )
        if latest_request:
            req, comp = latest_request
            if req.status == JoinRequestStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your request to join workspace '{comp.name}' is pending approval by the workspace owner.",
                )
            elif req.status == JoinRequestStatus.REJECTED:
                reason_msg = f" Reason: {req.rejection_reason}" if req.rejection_reason else ""
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your request to join workspace '{comp.name}' was not approved.{reason_msg}",
                )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to any active workspace. Please submit a request to join a workspace.",
        )

    token = create_access_token(subject=user.id)

    log_audit_event(
        db=db,
        action="LOGIN_SUCCESS",
        resource_type="user",
        user_id=user.id,
        details={"email": user.email},
        ip_address=ip_address,
    )
    db.commit()

    return user, token, companies_with_roles
