"""
认证 API 模块 - 登录与注册
=============================================================================
职责说明：
  提供用户身份认证相关的 HTTP 接口：
  1. POST /auth/register：用户注册（创建新账号）
  2. POST /auth/login：用户登录（获取 JWT Token）
  3. GET /auth/me：获取当前用户信息

典型场景：
  1. 新用户注册 -> POST /auth/register
  2. 注册成功后自动登录 -> POST /auth/login
  3. 后续请求带上 Token -> GET /auth/me 验证身份

安全设计：
  - 密码用 argon2 哈希存储（即使数据库泄露也拿不到明文）
  - JWT Token 有过期时间（24小时），过期需要重新登录
  - Token 验证在依赖注入层完成，路由函数只管业务逻辑
=============================================================================
"""
from typing import Optional

# FastAPI 核心
from fastapi import APIRouter, Depends, HTTPException, status

# Pydantic 数据验证
from pydantic import BaseModel, Field

# SQLAlchemy 查询
from sqlalchemy import select

# 异步数据库会话
from sqlalchemy.ext.asyncio import AsyncSession

# 导入数据库会话依赖
from app.core.db import get_async_session

# 导入安全工具：哈希密码、验证密码、创建 Token
from app.core.security import get_password_hash, verify_password, create_access_token

# 导入用户模型
from app.models.user import User

# 导入认证依赖：获取当前登录用户
from app.dependencies.auth import get_current_user

# 创建路由实例，prefix="/auth" 表示所有接口以 /auth 开头
# tags=["Authentication"] 在 Swagger 文档中分组显示
router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# 第 1 步：定义请求/响应模型（Pydantic）
# =============================================================================

# 为什么需要 Pydantic 模型？
#   1. 自动验证请求数据（如 username 长度、password 格式）
#   2. 自动生成 OpenAPI 文档（字段说明、类型）
#   3. IDE 自动补全（类型提示）
#   4. 数据转换（JSON -> Python 对象）

class RegisterRequest(BaseModel):
    """
    用户注册请求
    ==========================================================================
    字段说明：
      - username：用户名，3-50 个字符，用于登录
      - password：密码，6-100 个字符

    典型场景：
      前端表单填写 -> POST /auth/register {"username": "alice", "password": "pass123"}

    验证规则：
      - min_length/max_length：自动返回 422 错误如果不符合
      - Field(...)：... 表示必填字段
    """
    username: str = Field(..., min_length=3, max_length=50, description="用户名，3-50字符")
    password: str = Field(..., min_length=6, max_length=100, description="密码，6-100字符")


class LoginRequest(BaseModel):
    """
    用户登录请求
    ==========================================================================
    字段说明：
      - username：用户名
      - password：密码

    典型场景：
      前端表单填写 -> POST /auth/login {"username": "alice", "password": "pass123"}
      -> 验证成功返回 JWT Token
      -> 前端把 Token 存 localStorage，后续请求带上
    """
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """
    登录成功响应
    ==========================================================================
    字段说明：
      - access_token：JWT Token 字符串，客户端需要存储
      - token_type：固定为 "bearer"，HTTP 标准认证类型

    典型场景：
      前端收到 {"access_token": "eyJ...", "token_type": "bearer"}
      后续请求：Authorization: Bearer eyJ...
    """
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型，固定为 bearer")


class UserInfoResponse(BaseModel):
    """
    用户信息响应
    ==========================================================================
    字段说明：
      - id：用户 UUID（字符串形式）
      - username：用户名

    为什么不返回 password_hash？
      安全原则：永远不要把敏感数据返回给客户端
    """
    id: str = Field(..., description="用户ID（UUID）")
    username: str = Field(..., description="用户名")


class MessageResponse(BaseModel):
    """
    操作结果响应（通用）
    ==========================================================================
    字段说明：
      - message：操作结果描述

    典型场景：
      注册成功返回 {"message": "注册成功"}
    """
    message: str = Field(..., description="操作结果消息")


# =============================================================================
# 第 2 步：用户注册接口
# =============================================================================

@router.post("/register", response_model=MessageResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_session)
) -> MessageResponse:
    """
    用户注册

    ==========================================================================
    请求：POST /auth/register
    参数：RegisterRequest（username + password）
    依赖：db（数据库会话）

    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：检查用户名是否已存在 ----------
    SELECT * FROM users WHERE username = ?
    如果存在，返回 400 "用户名已存在"
    （为什么不返回更详细的信息？安全考虑，不告诉攻击者用户名是否存在）

    ---------- 第 2 步：哈希密码 ----------
    password_hash = get_password_hash(request.password)
    argon2 算法自动加盐哈希，返回类似 $argon2id$... 的字符串

    ---------- 第 3 步：创建用户记录 ----------
    INSERT INTO users (id, username, password_hash, created_at, updated_at)
    VALUES (uuid, ?, ?, NOW(), NOW())

    ---------- 第 4 步：提交事务 ----------
    await db.commit()
    如果用户名重复违反唯一约束，commit 时会抛异常

    ---------- 第 5 步：返回成功消息 ----------
    {"message": "注册成功"}

    典型场景：
      前端 POST {"username": "alice", "password": "pass123"}
      后端验证 -> 创建用户 -> 返回 "注册成功"
      用户再用同样账号登录获取 Token
    ==========================================================================
    """
    # ---------- 第 1 步：检查用户名唯一性 ----------
    # 使用 SQLAlchemy 的 select() API
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    existing_user = result.scalar_one_or_none()

    # 如果用户名已存在，返回 400 错误
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    # ---------- 第 2 步：哈希密码 ----------
    # 永远不要存明文密码！argon2 是目前最安全的哈希算法
    password_hash = get_password_hash(request.password)

    # ---------- 第 3 步：创建用户对象 ----------
    # 此时只是创建 Python 对象，还没有写入数据库
    new_user = User(
        username=request.username,
        password_hash=password_hash
    )

    # 将用户对象加入会话（此时生成 SQL INSERT，但不会立即执行）
    db.add(new_user)

    # ---------- 第 4 步：提交事务 ----------
    await db.commit()

    # ---------- 第 5 步：返回结果 ----------
    return MessageResponse(message="注册成功")


# =============================================================================
# 第 3 步：用户登录接口
# =============================================================================

@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_async_session)
) -> TokenResponse:
    """
    用户登录

    ==========================================================================
    请求：POST /auth/login
    参数：LoginRequest（username + password）
    依赖：db（数据库会话）

    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：查询用户 ----------
    SELECT * FROM users WHERE username = ?
    如果用户名不存在，scalar_one_or_none() 返回 None

    ---------- 第 2 步：验证密码 ----------
    verify_password(plain, hashed) -> bool
    - 如果用户不存在，返回 False（不单独判断，防止用户名枚举攻击）
    - 如果密码哈希不匹配，返回 False
    - 相同返回 True

    ---------- 第 3 步：创建 JWT Token ----------
    create_access_token({"sub": str(user.id)})
    - "sub" 字段存放用户 ID
    - Token 包含过期时间（24小时后）
    - 用 jwt_secret_key 签名

    ---------- 第 4 步：返回 Token ----------
    {"access_token": "eyJ...", "token_type": "bearer"}

    安全设计：
      - 无论用户名错还是密码错，都返回同样的错误信息
      - 不告诉攻击者是用户名错还是密码错

    典型场景：
      POST {"username": "alice", "password": "pass123"}
      -> 验证成功 -> 返回 Token
      -> 前端存储 Token 到 localStorage
      -> 后续所有请求带上 Authorization: Bearer <token>
    ==========================================================================
    """
    # ---------- 第 1 步：查询用户 ----------
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    # ---------- 第 2 步：验证密码 ----------
    # verify_password 内部比对哈希，无论用户存不存在都会执行
    # 这样可以防止"用户名枚举攻击"（通过不同错误信息猜测用户名）
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ---------- 第 3 步：创建 JWT Token ----------
    # {"sub": "user-uuid"} -> Token 字符串
    # "sub" 是 JWT 标准字段，存放用户主体标识
    access_token = create_access_token(data={"sub": str(user.id)})

    # ---------- 第 4 步：返回 Token ----------
    return TokenResponse(access_token=access_token)


# =============================================================================
# 第 4 步：获取当前用户信息
# =============================================================================

@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
) -> UserInfoResponse:
    """
    获取当前登录用户信息

    ==========================================================================
    请求：GET /auth/me
    依赖：current_user（通过 Depends(get_current_user) 自动注入）

    为什么用 Depends？
      FastAPI 的依赖注入系统：
      1. 调用 get_current_user()
      2. 自动从请求头提取 Token
      3. 验证 Token
      4. 查询数据库获取用户
      5. 返回 User 对象给路由函数

    为什么不用手动提取 Token？
      代码更简洁，业务逻辑和认证逻辑分离
      认证逻辑只需要写一次

    典型场景：
      前端请求 GET /auth/me
      Header: Authorization: Bearer <token>
      -> 验证 Token -> 返回 {"id": "xxx", "username": "alice"}
      -> 前端显示用户信息
    ==========================================================================
    """
    return UserInfoResponse(
        id=str(current_user.id),
        username=current_user.username
    )
