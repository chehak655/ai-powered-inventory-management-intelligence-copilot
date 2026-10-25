from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.company import Company
from app.models.membership import CompanyMember, MemberRole

security = HTTPBearer(auto_error=False)


@dataclass
class WorkspaceContext:
    company: Company
    member: CompanyMember
    role: MemberRole
    user: User


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP address safely from request headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Validate Bearer JWT token and return active authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


def get_current_workspace(
    x_company_id: Optional[str] = Header(None, alias="X-Company-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    """
    Validate active workspace for current user.
    Strictly verifies user's active membership against the requested company ID.
    Never trusts the header blindly.
    """
    if not x_company_id:
        # Check user's memberships
        memberships = (
            db.query(CompanyMember)
            .filter(CompanyMember.user_id == current_user.id)
            .all()
        )
        if len(memberships) == 1:
            x_company_id = memberships[0].company_id
        elif len(memberships) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to any workspace.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Company-Id header is required to select active workspace from multiple memberships.",
            )

    # Strictly query membership to enforce multi-tenant isolation
    membership = (
        db.query(CompanyMember, Company)
        .join(Company, CompanyMember.company_id == Company.id)
        .filter(
            CompanyMember.company_id == x_company_id,
            CompanyMember.user_id == current_user.id,
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not an authorized member of this company workspace.",
        )

    member, company = membership
    return WorkspaceContext(
        company=company,
        member=member,
        role=member.role,
        user=current_user,
    )


def require_owner(
    workspace_context: WorkspaceContext = Depends(get_current_workspace),
) -> WorkspaceContext:
    """Ensure the authenticated user holds an OWNER role in the current workspace."""
    if workspace_context.role != MemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Owner role required for this action.",
        )
    return workspace_context
