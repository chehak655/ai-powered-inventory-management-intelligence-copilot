from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_client_ip, get_current_user
from app.models.user import User
from app.models.company import Company
from app.models.membership import CompanyMember
from app.schemas.auth import (
    OwnerRegisterRequest,
    LoginRequest,
    TokenResponse,
    LogoutResponse,
)
from app.schemas.user import UserResponse
from app.schemas.company import CompanyResponse
from app.schemas.join_request import WorkerJoinRequestSubmit, JoinRequestResponse
from app.services.auth_service import register_owner, authenticate_user
from app.services.workspace_service import create_worker_join_request

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new owner and workspace",
)
def register(
    request: OwnerRegisterRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """
    Register a new company workspace and its initial Owner account.
    Fails atomically if the email exists.
    """
    ip_addr = get_client_ip(raw_request)
    user, company, token = register_owner(db, request, ip_address=ip_addr)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        companies=[
            CompanyResponse(
                id=company.id,
                name=company.name,
                slug=company.slug,
                role="OWNER",
                created_at=company.created_at,
            )
        ],
    )


@router.post(
    "/join-request",
    response_model=JoinRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Worker self-registration request to join a workspace",
)
def submit_join_request(
    request: WorkerJoinRequestSubmit,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """
    Submit a request for a worker account to join an existing company workspace.
    Creates a pending join request that requires owner approval before access is granted.
    """
    ip_addr = get_client_ip(raw_request)
    return create_worker_join_request(db=db, request=request, ip_address=ip_addr)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
)
def login(
    request: LoginRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate with user credentials and retrieve access token and workspace memberships."""
    ip_addr = get_client_ip(raw_request)
    user, token, companies_with_roles = authenticate_user(db, request, ip_address=ip_addr)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        companies=[
            CompanyResponse(
                id=comp.id,
                name=comp.name,
                slug=comp.slug,
                role=str(role.value),
                created_at=comp.created_at,
            )
            for comp, role in companies_with_roles
        ],
    )


@router.get(
    "/me",
    summary="Get current authenticated user profile and memberships",
)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve profile and list of workspaces for the current user."""
    memberships = (
        db.query(CompanyMember, Company)
        .join(Company, CompanyMember.company_id == Company.id)
        .filter(CompanyMember.user_id == current_user.id)
        .all()
    )

    return {
        "user": UserResponse.model_validate(current_user),
        "companies": [
            CompanyResponse(
                id=comp.id,
                name=comp.name,
                slug=comp.slug,
                role=str(member.role.value),
                created_at=comp.created_at,
            )
            for member, comp in memberships
        ],
    }


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out of application",
)
def logout(
    current_user: User = Depends(get_current_user),
):
    """
    Stateless JWT logout confirmation.
    Clients should discard the access token from secure client storage.
    """
    return LogoutResponse(message="Logged out successfully. Please clear your access token.")
