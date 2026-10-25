from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.company import Company
from app.models.membership import CompanyMember, MemberRole
from app.models.join_request import WorkspaceJoinRequest, JoinRequestStatus
from app.schemas.membership import AddWorkerRequest, MemberResponse, UpdateRoleRequest
from app.schemas.join_request import WorkerJoinRequestSubmit, JoinRequestResponse
from app.core.security import hash_password, verify_password
from app.services.audit_service import log_audit_event


def add_worker_to_company(
    db: Session,
    company: Company,
    request: AddWorkerRequest,
    current_user: User,
    ip_address: Optional[str] = None
) -> MemberResponse:
    """Add a new or existing user as a worker to the specified company workspace."""
    email_clean = request.email.lower().strip()
    user = db.query(User).filter(User.email == email_clean).first()

    if not user:
        # Create user account for the new worker
        user = User(
            email=email_clean,
            hashed_password=hash_password(request.password),
            full_name=request.full_name.strip(),
            is_active=True,
        )
        db.add(user)
        db.flush()

    # Check if membership already exists
    existing_member = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_id == user.id
        )
        .first()
    )
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {user.email} is already a member of workspace '{company.name}'."
        )

    # Create membership record - enforce WORKER role for newly added workers
    membership = CompanyMember(
        company_id=company.id,
        user_id=user.id,
        role=MemberRole.WORKER,
    )
    db.add(membership)

    log_audit_event(
        db=db,
        action="WORKSPACE_MEMBER_ADDED",
        resource_type="company_member",
        company_id=company.id,
        user_id=current_user.id,
        resource_id=membership.id,
        details={
            "added_user_id": user.id,
            "added_user_email": user.email,
            "role": str(MemberRole.WORKER.value),
        },
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(membership)

    return MemberResponse(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
        is_active=user.is_active,
    )


def list_company_members(db: Session, company_id: str) -> List[MemberResponse]:
    """Retrieve all members of a specific company workspace."""
    results = (
        db.query(CompanyMember, User)
        .join(User, CompanyMember.user_id == User.id)
        .filter(CompanyMember.company_id == company_id)
        .order_by(CompanyMember.created_at.asc())
        .all()
    )

    return [
        MemberResponse(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            created_at=member.created_at,
            is_active=user.is_active,
        )
        for member, user in results
    ]


def update_member_role(
    db: Session,
    company: Company,
    target_member_id: str,
    request: UpdateRoleRequest,
    current_user: User,
    ip_address: Optional[str] = None
) -> MemberResponse:
    """Update a workspace member's role (Owner only)."""
    membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.id == target_member_id,
            CompanyMember.company_id == company.id
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace membership record not found."
        )

    # Protect against demoting the sole owner
    if membership.role == MemberRole.OWNER and request.role != MemberRole.OWNER:
        owner_count = (
            db.query(CompanyMember)
            .filter(
                CompanyMember.company_id == company.id,
                CompanyMember.role == MemberRole.OWNER
            )
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last owner of the workspace."
            )

    membership.role = request.role
    log_audit_event(
        db=db,
        action="WORKSPACE_ROLE_UPDATED",
        resource_type="company_member",
        company_id=company.id,
        user_id=current_user.id,
        resource_id=membership.id,
        details={"target_user_id": membership.user_id, "new_role": str(request.role)},
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(membership)

    user = db.query(User).filter(User.id == membership.user_id).first()
    return MemberResponse(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
        is_active=user.is_active,
    )


def create_worker_join_request(
    db: Session,
    request: WorkerJoinRequestSubmit,
    ip_address: Optional[str] = None
) -> JoinRequestResponse:
    """Submit a request for a worker to join an existing company workspace."""
    email_clean = request.email.lower().strip()
    slug_clean = request.workspace_slug.lower().strip()

    # Find the target company by slug or name
    company = (
        db.query(Company)
        .filter(or_(func.lower(Company.slug) == slug_clean, func.lower(Company.name) == slug_clean))
        .first()
    )
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{request.workspace_slug}' does not exist. Please check the identifier with your administrator."
        )

    # Check if user account exists
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        user = User(
            email=email_clean,
            hashed_password=hash_password(request.password),
            full_name=request.full_name.strip(),
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        # Existing account: verify password to prevent unauthorized impersonation
        if not verify_password(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid credentials for the provided email address."
            )

    # Check if user is already a member
    existing_membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_id == user.id,
        )
        .first()
    )
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You are already a member of workspace '{company.name}'."
        )

    # Check if user already has a pending join request for this company
    pending_req = (
        db.query(WorkspaceJoinRequest)
        .filter(
            WorkspaceJoinRequest.company_id == company.id,
            WorkspaceJoinRequest.user_id == user.id,
            WorkspaceJoinRequest.status == JoinRequestStatus.PENDING,
        )
        .first()
    )
    if pending_req:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A join request for workspace '{company.name}' is already pending review by the owner."
        )

    # Create join request
    join_req = WorkspaceJoinRequest(
        company_id=company.id,
        user_id=user.id,
        email=email_clean,
        full_name=request.full_name.strip() if not user else user.full_name,
        status=JoinRequestStatus.PENDING,
    )
    db.add(join_req)
    db.flush()

    log_audit_event(
        db=db,
        action="WORKSPACE_JOIN_REQUEST_SUBMITTED",
        resource_type="workspace_join_request",
        company_id=company.id,
        user_id=user.id,
        resource_id=join_req.id,
        details={
            "requester_email": user.email,
            "company_name": company.name,
            "company_slug": company.slug,
        },
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(join_req)

    return JoinRequestResponse(
        id=join_req.id,
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        user_id=user.id,
        email=join_req.email,
        full_name=join_req.full_name,
        status=join_req.status.value,
        created_at=join_req.created_at,
        reviewed_at=join_req.reviewed_at,
        reviewed_by_id=join_req.reviewed_by_id,
        rejection_reason=join_req.rejection_reason,
        message=f"Your request to join '{company.name}' has been submitted and is pending approval by the workspace owner.",
    )


def list_workspace_join_requests(
    db: Session,
    company_id: str,
    status_filter: Optional[str] = None
) -> List[JoinRequestResponse]:
    """List join requests for a specific workspace. Owner only."""
    query = (
        db.query(WorkspaceJoinRequest, Company)
        .join(Company, WorkspaceJoinRequest.company_id == Company.id)
        .filter(WorkspaceJoinRequest.company_id == company_id)
    )

    if status_filter:
        query = query.filter(WorkspaceJoinRequest.status == status_filter.upper())

    results = query.order_by(WorkspaceJoinRequest.created_at.desc()).all()

    return [
        JoinRequestResponse(
            id=req.id,
            company_id=comp.id,
            company_name=comp.name,
            company_slug=comp.slug,
            user_id=req.user_id,
            email=req.email,
            full_name=req.full_name,
            status=req.status.value,
            created_at=req.created_at,
            reviewed_at=req.reviewed_at,
            reviewed_by_id=req.reviewed_by_id,
            rejection_reason=req.rejection_reason,
        )
        for req, comp in results
    ]


def approve_join_request(
    db: Session,
    company_id: str,
    request_id: str,
    reviewer_user: User,
    ip_address: Optional[str] = None
) -> JoinRequestResponse:
    """Approve a pending join request, adding the worker to the workspace atomically. Owner only."""
    req = (
        db.query(WorkspaceJoinRequest)
        .filter(
            WorkspaceJoinRequest.id == request_id,
            WorkspaceJoinRequest.company_id == company_id,
        )
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Join request not found for this workspace."
        )

    if req.status != JoinRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Join request has already been reviewed (status: {req.status.value})."
        )

    # Check if membership already exists to guarantee idempotency
    existing_member = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == req.user_id,
        )
        .first()
    )
    if not existing_member:
        new_member = CompanyMember(
            company_id=company_id,
            user_id=req.user_id,
            role=MemberRole.WORKER,
        )
        db.add(new_member)

    # Mark approved
    req.status = JoinRequestStatus.APPROVED
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by_id = reviewer_user.id

    log_audit_event(
        db=db,
        action="WORKSPACE_JOIN_REQUEST_APPROVED",
        resource_type="workspace_join_request",
        company_id=company_id,
        user_id=reviewer_user.id,
        resource_id=req.id,
        details={
            "approved_user_id": req.user_id,
            "approved_email": req.email,
            "reviewer_user_id": reviewer_user.id,
        },
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(req)

    company = db.query(Company).filter(Company.id == company_id).first()

    return JoinRequestResponse(
        id=req.id,
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        user_id=req.user_id,
        email=req.email,
        full_name=req.full_name,
        status=req.status.value,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
        reviewed_by_id=req.reviewed_by_id,
        rejection_reason=req.rejection_reason,
        message=f"Join request for {req.full_name} ({req.email}) approved successfully.",
    )


def reject_join_request(
    db: Session,
    company_id: str,
    request_id: str,
    reviewer_user: User,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None
) -> JoinRequestResponse:
    """Reject a pending join request. Owner only."""
    req = (
        db.query(WorkspaceJoinRequest)
        .filter(
            WorkspaceJoinRequest.id == request_id,
            WorkspaceJoinRequest.company_id == company_id,
        )
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Join request not found for this workspace."
        )

    if req.status != JoinRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Join request has already been reviewed (status: {req.status.value})."
        )

    req.status = JoinRequestStatus.REJECTED
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by_id = reviewer_user.id
    req.rejection_reason = reason.strip() if reason else None

    log_audit_event(
        db=db,
        action="WORKSPACE_JOIN_REQUEST_REJECTED",
        resource_type="workspace_join_request",
        company_id=company_id,
        user_id=reviewer_user.id,
        resource_id=req.id,
        details={
            "rejected_user_id": req.user_id,
            "rejected_email": req.email,
            "reason": req.rejection_reason,
            "reviewer_user_id": reviewer_user.id,
        },
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(req)

    company = db.query(Company).filter(Company.id == company_id).first()

    return JoinRequestResponse(
        id=req.id,
        company_id=company.id,
        company_name=company.name,
        company_slug=company.slug,
        user_id=req.user_id,
        email=req.email,
        full_name=req.full_name,
        status=req.status.value,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
        reviewed_by_id=req.reviewed_by_id,
        rejection_reason=req.rejection_reason,
        message=f"Join request for {req.full_name} ({req.email}) rejected.",
    )
