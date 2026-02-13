"""Authentication API Endpoints"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import AuthService
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenResponse,
    RegisterRequest,
    CustomerRegisterRequest,
    UserInfo,
    GuestTokenResponse
)
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.chat_service import ChatService
import uuid


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    x_device_id: str | None = Header(None, alias="X-Device-ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT tokens.
    
    - **username**: User's username
    - **password**: User's password
    
    Returns access token, refresh token, and user info.
    """
    user = await AuthService.authenticate_user(
        db, request.username, request.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login timestamp
    await AuthService.update_last_login(db, user)
    
    # Create tokens
    access_token, refresh_token, expires_in = AuthService.create_tokens(
        user.id, user.username
    )
    
    # Migrate guest conversations if visitor_id provided
    to_customer_id = f"user_{user.id}"
    await ChatService.migrate_guest_conversations(
        db=db,
        to_customer_id=to_customer_id,
        visitor_id=request.visitor_id,
        device_id=request.guest_device_id or x_device_id,
        conversation_ids=request.guest_conversation_ids,
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserInfo.model_validate(user)
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    - **refresh_token**: Valid refresh token
    
    Returns new access token and refresh token.
    """
    # Verify refresh token
    payload = AuthService.verify_token(request.refresh_token, token_type="refresh")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from token
    user_id = int(payload.get("sub"))
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new tokens
    access_token, refresh_token, expires_in = AuthService.create_tokens(
        user.id, user.username
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submit user registration request (requires admin approval).
    
    - **username**: Desired username (3-50 characters)
    - **password**: Password (minimum 6 characters)
    - **display_name**: Display name
    - **email**: Optional email address
    
    Returns success message. Account will be inactive until approved.
    """
    # Check if username already exists
    existing_user = await AuthService.get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在"
        )
    
    # Create user with is_active=False (pending approval)
    await AuthService.create_user(
        db=db,
        username=request.username,
        password=request.password,
        display_name=request.display_name,
        email=request.email,
        role="cs",
        is_active=False
    )
    
    return {"message": "注册申请已提交，请等待管理员审批"}


@router.post("/register-customer", status_code=status.HTTP_201_CREATED)
async def register_customer(
    request: CustomerRegisterRequest,
    x_device_id: str | None = Header(None, alias="X-Device-ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new customer account (no admin approval needed).
    Optionally migrates guest conversations to the new account.
    """
    # Check if username already exists
    existing_user = await AuthService.get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在"
        )
    
    # Create customer user with is_active=True (no approval needed)
    user = await AuthService.create_user(
        db=db,
        username=request.username,
        password=request.password,
        display_name=request.display_name,
        email=None,
        role="customer",
        is_active=True
    )
    
    # Migrate guest conversations if visitor_id provided
    to_customer_id = f"user_{user.id}"
    await ChatService.migrate_guest_conversations(
        db=db,
        to_customer_id=to_customer_id,
        visitor_id=request.visitor_id,
        device_id=request.guest_device_id or x_device_id,
        conversation_ids=request.guest_conversation_ids,
    )
    
    # Auto-login: create tokens
    access_token, refresh_token, expires_in = AuthService.create_tokens(
        user.id, user.username
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserInfo.model_validate(user)
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's information.
    
    Requires valid access token in Authorization header.
    """
    return UserInfo.model_validate(current_user)


@router.post("/guest", response_model=GuestTokenResponse)
async def get_guest_token():
    """
    Issue a guest visitor token for anonymous customers.
    
    Returns a short-lived JWT with a unique visitor_id.
    No credentials required.
    """
    from datetime import timedelta
    
    visitor_id = f"visitor_{uuid.uuid4().hex[:12]}"
    
    token = AuthService.create_access_token(
        data={"sub": visitor_id, "role": "guest"},
        expires_delta=timedelta(days=7)
    )
    
    return GuestTokenResponse(
        access_token=token,
        expires_in=7 * 24 * 3600,
        visitor_id=visitor_id
    )
