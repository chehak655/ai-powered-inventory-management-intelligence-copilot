from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    WorkspaceContext,
    get_client_ip,
    get_current_user,
    get_current_workspace,
    require_owner,
)
from app.models.user import User
from app.models.company import Company
from app.models.membership import CompanyMember
from app.models.audit_log import AuditLog
from app.schemas.company import CompanyResponse
from app.schemas.membership import AddWorkerRequest, MemberResponse, UpdateRoleRequest
from app.schemas.audit_log import AuditLogResponse
from app.schemas.join_request import JoinRequestResponse, RejectJoinRequestPayload
from app.services.workspace_service import (
    add_worker_to_company,
    list_company_members,
    update_member_role,
    list_workspace_join_requests,
    approve_join_request,
    reject_join_request,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces & Membership"])


@router.get(
    "/",
    response_model=List[CompanyResponse],
    summary="List all workspaces current user has access to",
)
def list_my_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all company workspaces where current user is an active member."""
    memberships = (
        db.query(CompanyMember, Company)
        .join(Company, CompanyMember.company_id == Company.id)
        .filter(CompanyMember.user_id == current_user.id)
        .all()
    )

    return [
        CompanyResponse(
            id=comp.id,
            name=comp.name,
            slug=comp.slug,
            role=str(member.role.value),
            created_at=comp.created_at,
        )
        for member, comp in memberships
    ]


@router.get(
    "/current",
    response_model=CompanyResponse,
    summary="Get current active workspace details",
)
def get_current_workspace_info(
    ctx: WorkspaceContext = Depends(get_current_workspace),
):
    """Retrieve details and role for the currently selected active workspace."""
    return CompanyResponse(
        id=ctx.company.id,
        name=ctx.company.name,
        slug=ctx.company.slug,
        role=str(ctx.role.value),
        created_at=ctx.company.created_at,
    )


@router.get(
    "/members",
    response_model=List[MemberResponse],
    summary="List all members in the current workspace",
)
def get_members(
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """List all members belonging to the active workspace."""
    return list_company_members(db, ctx.company.id)


@router.post(
    "/workers",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a worker to the current workspace (Owner only)",
)
def add_worker(
    request: AddWorkerRequest,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Add a new or existing user as a worker in this workspace. Owner only."""
    ip_addr = get_client_ip(raw_request)
    return add_worker_to_company(
        db=db,
        company=ctx.company,
        request=request,
        current_user=ctx.user,
        ip_address=ip_addr,
    )


@router.put(
    "/members/{member_id}/role",
    response_model=MemberResponse,
    summary="Update a member's role (Owner only)",
)
def change_member_role(
    member_id: str,
    request: UpdateRoleRequest,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Change a member's role between WORKER and OWNER. Owner only."""
    ip_addr = get_client_ip(raw_request)
    return update_member_role(
        db=db,
        company=ctx.company,
        target_member_id=member_id,
        request=request,
        current_user=ctx.user,
        ip_address=ip_addr,
    )


@router.get(
    "/audit",
    response_model=List[AuditLogResponse],
    summary="View company audit history (Owner only)",
)
def get_company_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Retrieve audit log history for this workspace. Owner only."""
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.company_id == ctx.company.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [AuditLogResponse.model_validate(log) for log in logs]


@router.get(
    "/join-requests",
    response_model=List[JoinRequestResponse],
    summary="List workspace join requests (Owner only)",
)
def get_join_requests(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPROVED, REJECTED)"),
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Retrieve membership join requests for this workspace. Owner only."""
    return list_workspace_join_requests(db=db, company_id=ctx.company.id, status_filter=status)


@router.post(
    "/join-requests/{request_id}/approve",
    response_model=JoinRequestResponse,
    summary="Approve a worker join request (Owner only)",
)
def approve_request(
    request_id: str,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Approve a worker's request to join this workspace, assigning them the WORKER role. Owner only."""
    ip_addr = get_client_ip(raw_request)
    return approve_join_request(
        db=db,
        company_id=ctx.company.id,
        request_id=request_id,
        reviewer_user=ctx.user,
        ip_address=ip_addr,
    )


@router.post(
    "/join-requests/{request_id}/reject",
    response_model=JoinRequestResponse,
    summary="Reject a worker join request (Owner only)",
)
def reject_request(
    request_id: str,
    payload: RejectJoinRequestPayload,
    raw_request: Request,
    ctx: WorkspaceContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Reject a worker's request to join this workspace. Owner only."""
    ip_addr = get_client_ip(raw_request)
    return reject_join_request(
        db=db,
        company_id=ctx.company.id,
        request_id=request_id,
        reviewer_user=ctx.user,
        reason=payload.reason,
        ip_address=ip_addr,
    )
