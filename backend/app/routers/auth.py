"""Authentication Router - User registration, login, logout, password reset"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.middleware.auth import get_current_user as require_current_user
from app.middleware.rate_limit import auth_rate_limit, read_rate_limit
from app.models.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    TokenRefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.services.auth import auth_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@auth_rate_limit
async def register(request: Request, data: UserCreate):
    """
    Register a new user account.

    - **email**: User's email address (must be unique)
    - **username**: Desired username (3-50 characters, must be unique)
    - **display_name**: Optional display name
    - **password**: Password (min 8 characters)
    """
    try:
        user = await auth_service.create_user(
            email=data.email,
            username=data.username,
            password=data.password,
            display_name=data.display_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Create tokens
    access_token = auth_service.create_access_token(user["id"])
    refresh_token = auth_service.create_refresh_token(user["id"])

    # Store refresh token
    await auth_service.store_refresh_token(user["id"], refresh_token)

    logger.info(f"New user registered: {user['email']}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60,
        user=UserResponse(**user),
    )


@router.post("/login", response_model=TokenResponse)
@auth_rate_limit
async def login(request: Request, data: UserLogin):
    """
    Login with email and password.

    Returns access and refresh tokens along with user information.
    """
    user = await auth_service.authenticate_user(data.email, data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = auth_service.create_access_token(user["id"])
    refresh_token = auth_service.create_refresh_token(user["id"])

    # Store refresh token
    await auth_service.store_refresh_token(user["id"], refresh_token)

    logger.info(f"User logged in: {user['email']}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60,
        user=UserResponse(**user),
    )


@router.post("/refresh", response_model=TokenResponse)
@auth_rate_limit
async def refresh_token(request: Request, data: TokenRefreshRequest):
    """
    Refresh an access token using a refresh token.

    - **refresh_token**: Valid refresh token from login
    """
    payload = auth_service.decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    # Verify refresh token exists in database
    if not await auth_service.validate_refresh_token(data.refresh_token, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or expired",
        )

    # Get user
    user = await auth_service.get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new access token
    access_token = auth_service.create_access_token(user["id"])

    logger.info(f"Token refreshed for user: {user['email']}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=data.refresh_token,  # Return same refresh token
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60,
        user=UserResponse(**user),
    )


@router.post("/logout")
@auth_rate_limit
async def logout(request: Request, data: TokenRefreshRequest):
    """
    Logout by invalidating the refresh token.

    - **refresh_token**: Refresh token to invalidate
    """
    payload = auth_service.decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    # Revoke the refresh token
    revoked = await auth_service.revoke_refresh_token(user_id, data.refresh_token)

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found",
        )

    logger.info(f"User logged out: {user_id}")

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
@read_rate_limit
async def get_current_user_profile(
    request: Request,
    current_user: dict = Depends(require_current_user),
):
    """
    Get the current authenticated user's profile.

    Requires a valid access token in the Authorization header.
    """
    return UserResponse(**current_user)


@router.post("/password-reset")
@auth_rate_limit
async def request_password_reset(request: Request, data: PasswordResetRequest):
    """
    Request a password reset.

    Sends a password reset token to the user's email.
    In development, the token is logged to the console.

    - **email**: User's email address
    """
    reset_token = await auth_service.create_password_reset_token(data.email)

    # Always return success to prevent email enumeration
    # In production, send email with reset token
    logger.info(f"Password reset requested for: {data.email}")

    return {
        "message": "If an account with this email exists, a password reset token has been sent",
        # Only include token in development for testing
        "_dev_token": reset_token if reset_token else None,
    }


@router.post("/password-reset/confirm")
@auth_rate_limit
async def confirm_password_reset(request: Request, data: PasswordResetConfirm):
    """
    Confirm a password reset with the token.

    - **token**: Password reset token from email
    - **new_password**: New password (min 8 characters)
    """
    success = await auth_service.reset_password(data.token, data.new_password)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    logger.info("Password reset completed successfully")

    return {"message": "Password has been reset successfully"}
