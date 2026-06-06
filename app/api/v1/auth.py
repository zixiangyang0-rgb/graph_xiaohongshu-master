"""
认证接口：注册、登录、获取当前用户。

这里不做复杂逻辑，主要就是校验参数、查库、发 token。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    """注册参数。"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名，3-50字符")
    password: str = Field(..., min_length=6, max_length=100, description="密码，6-100字符")


class LoginRequest(BaseModel):
    """登录参数。"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """登录成功后返回的 token。"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型，固定为 bearer")


class UserInfoResponse(BaseModel):
    """当前用户信息。"""
    id: str = Field(..., description="用户ID（UUID）")
    username: str = Field(..., description="用户名")


class MessageResponse(BaseModel):
    """通用消息返回。"""
    message: str = Field(..., description="操作结果消息")


@router.post("/register", response_model=MessageResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_session)
) -> MessageResponse:
    """创建账号。"""
    # 检查用户名唯一性
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    # 只返回通用错误，避免把用户名是否存在暴露得太明确
    password_hash = get_password_hash(request.password)

    new_user = User(
        username=request.username,
        password_hash=password_hash
    )

    db.add(new_user)
    await db.commit()

    return MessageResponse(message="注册成功")


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_async_session)
) -> TokenResponse:
    """用户名密码登录，并返回 access token。"""
    # 查询用户
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    # 用户不存在和密码错误都返回同一条信息
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
) -> UserInfoResponse:
    """返回当前登录用户的基本信息。"""
    return UserInfoResponse(
        id=str(current_user.id),
        username=current_user.username
    )
