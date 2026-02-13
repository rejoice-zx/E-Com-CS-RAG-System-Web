# -*- coding: utf-8 -*-
"""
用户管理API端点 - User Management API Endpoints

功能:
- 用户CRUD操作
- 注册审批
- 密码重置
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime, timezone

from app.database import get_db
from app.models.user import User
from app.services.auth_service import AuthService
from app.api.dependencies import AdminRequired
from pydantic import BaseModel, Field, EmailStr


router = APIRouter(prefix="/api/users", tags=["Users"])


# ==================== Schemas ====================

class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    role: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """用户列表响应"""
    items: List[UserResponse]
    total: int
    page: int
    page_size: int


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    role: str = Field(default="cs", pattern="^(admin|cs|customer)$")


class UpdateUserRequest(BaseModel):
    """更新用户请求"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern="^(admin|cs|customer)$")
    is_active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    password: str = Field(..., min_length=6)


# ==================== API Endpoints ====================

@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    role: Optional[str] = Query(None, description="角色筛选"),
    is_active: Optional[bool] = Query(None, description="状态筛选"),
    username: Optional[str] = Query(None, description="用户名搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    
    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
        count_stmt = count_stmt.where(User.is_active == is_active)
    
    if username:
        stmt = stmt.where(User.username.ilike(f"%{username}%"))
        count_stmt = count_stmt.where(User.username.ilike(f"%{username}%"))
    
    # 按角色排序：admin > cs > customer，同角色按创建时间降序
    from sqlalchemy import case
    role_order = case(
        (User.role == "admin", 0),
        (User.role == "cs", 1),
        else_=2
    )
    stmt = stmt.order_by(role_order, User.id.asc())
    
    # 分页
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    
    # 执行查询
    result = await db.execute(stmt)
    users = list(result.scalars().all())
    
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/pending", response_model=List[UserResponse])
async def get_pending_registrations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    获取待审批的注册申请
    
    Returns: 待审批用户列表
    """
    stmt = select(User).where(User.is_active == False)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    获取用户详情
    
    - **user_id**: 用户ID
    
    Returns: 用户详细信息
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    创建新用户（管理员直接创建，无需审批）
    
    - **username**: 用户名（3-50字符）
    - **password**: 密码（至少6字符）
    - **display_name**: 显示名称
    - **email**: 邮箱（可选）
    - **role**: 角色（admin或cs）
    
    Returns: 新创建的用户信息
    """
    # 检查用户名是否已存在
    existing_user = await AuthService.get_user_by_username(db, request.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在"
        )
    
    # 创建用户（直接激活）
    user = await AuthService.create_user(
        db=db,
        username=request.username,
        password=request.password,
        display_name=request.display_name,
        email=request.email,
        role=request.role,
        is_active=True
    )
    
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    更新用户信息
    
    - **user_id**: 用户ID
    - **display_name**: 新显示名称（可选）
    - **email**: 新邮箱（可选）
    - **role**: 新角色（可选）
    - **is_active**: 新状态（可选）
    
    Returns: 更新后的用户信息
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不允许修改自己的角色和状态
    if user.id == current_user.id:
        if request.role is not None and request.role != user.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能修改自己的角色"
            )
        if request.is_active is not None and request.is_active != user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能修改自己的状态"
            )
    
    # 更新字段
    if request.display_name is not None:
        user.display_name = request.display_name
    if request.email is not None:
        user.email = request.email
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    删除用户
    
    - **user_id**: 用户ID
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不允许删除自己
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己"
        )
    
    # 只有超级管理员(username=admin)才能删除其他管理员
    if user.role == "admin" and current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员才能删除其他管理员"
        )
    
    await db.delete(user)
    await db.commit()


@router.post("/{user_id}/approve", response_model=UserResponse)
async def approve_registration(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    审批通过注册申请
    
    - **user_id**: 用户ID
    
    Returns: 更新后的用户信息
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已激活"
        )
    
    user.is_active = True
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_registration(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    拒绝注册申请（删除用户）
    
    - **user_id**: 用户ID
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能拒绝已激活的用户"
        )
    
    await db.delete(user)
    await db.commit()


@router.post("/{user_id}/reset-password", response_model=UserResponse)
async def reset_password(
    user_id: int,
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(AdminRequired)
):
    """
    重置用户密码
    
    - **user_id**: 用户ID
    - **password**: 新密码（至少6字符）
    
    Returns: 用户信息
    """
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user.password_hash = AuthService.hash_password(request.password)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)
