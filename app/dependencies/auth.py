"""
认证依赖模块 - 获取当前登录用户
=============================================================================
职责说明：
  提供 FastAPI 依赖注入函数，从请求中提取当前登录用户信息。

核心设计：
  - HTTPBearer：HTTP 标准认证方案（Authorization: Bearer <token>）
  - JWT Token：用户登录后拿到的令牌，包含了用户身份信息
  - 依赖注入：FastAPI 的核心特性，把认证逻辑从路由中分离

工作流程：
  1. 从请求头读取 Authorization: Bearer <token>
  2. 解码 JWT Token，验证签名和过期时间
  3. 从 Token 的 "sub" 字段取出用户 ID
  4. 查询数据库获取完整用户信息
  5. 返回 User 对象给路由函数使用

典型场景：
  @app.get("/profile")
  async def get_profile(current_user: User = Depends(get_current_user)):
      return {"user": current_user.username}
  访问这个接口时，如果没带 Token 或 Token 无效，返回 401
=============================================================================
"""
from typing import Optional

# FastAPI 核心依赖注入
# Depends：声明依赖关系，自动调用依赖函数并注入结果
# HTTPException：抛出 HTTP 错误
# status：HTTP 状态码常量
from fastapi import Depends, HTTPException, status

# HTTP 认证方案
# HTTPBearer：处理 Authorization: Bearer <token> 格式
# HTTPAuthorizationCredentials：解析后的凭证对象
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# SQLAlchemy 查询工具
from sqlalchemy import select

# 异步数据库会话
from sqlalchemy.ext.asyncio import AsyncSession

# 导入数据库会话依赖
from app.core.db import get_async_session

# 导入 JWT 工具
from app.core.security import decode_access_token

# 导入用户模型
from app.models.user import User


# =============================================================================
# 第 1 步：创建认证方案
# =============================================================================

# HTTPBearer：处理 Bearer Token 认证
# auto_error=True：没有 Token 时自动返回 401（必须带 Token）
# auto_error=False：没有 Token 时不报错，返回 None（用于可选认证）
security = HTTPBearer()


# =============================================================================
# 第 2 步：获取当前登录用户（必须认证）
# =============================================================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """
    获取当前登录用户（FastAPI 依赖注入）

    ==========================================================================
    使用方式：
      在需要认证的路由函数参数中使用：
      async def get_item(item_id: int, current_user: User = Depends(get_current_user))

    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：解析 Authorization 头 ----------
    HTTP 请求格式：Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...
    HTTPBearer 自动解析，credentials.credentials 就是 Token 字符串

    ---------- 第 2 步：解码 JWT Token ----------
    调用 decode_access_token() 验证 Token 签名和过期时间
    成功：返回载荷字典 {"sub": "user-uuid", "exp": ...}
    失败：返回 None

    ---------- 第 3 步：提取用户 ID ----------
    从 Token 载荷中取 "sub" 字段，即用户的 UUID 字符串

    ---------- 第 4 步：查询数据库 ----------
    用用户 ID 查询 users 表，获取完整的用户对象

    ---------- 第 5 步：返回用户对象 ----------
    如果所有步骤都成功，返回 User 对象给路由函数使用

    错误处理：
      - Token 格式错误/签名错误/过期：返回 401
      - 用户 ID 不存在（可能用户被删了）：返回 401
      - 数据库查询失败：返回 500

    典型场景：
      用户登录后，每次请求带上 Token
      后端验证 Token -> 取出用户 ID -> 查询用户信息 -> 执行业务逻辑
    ==========================================================================
    """
    # 认证失败的默认响应（不暴露具体原因）
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ---------- 第 1 步：获取 Token ----------
    # credentials 由 HTTPBearer 自动从请求头解析
    # credentials.credentials 就是 Token 字符串（去掉 "Bearer " 前缀）
    token = credentials.credentials

    # ---------- 第 2 步：解码并验证 Token ----------
    # decode_access_token() 验证签名和过期时间
    # 成功返回 {"sub": "user-uuid", "exp": ...}
    # 失败返回 None
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    # ---------- 第 3 步：提取用户 ID ----------
    # "sub" 是 JWT 标准字段，存放用户的主体标识（这里是用户 UUID 字符串）
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        # Token 没有 "sub" 字段，说明不是有效的认证 Token
        raise credentials_exception

    # ---------- 第 4 步：查询数据库获取用户 ----------
    # 使用 SQLAlchemy 的 select() API（推荐，比 filter() 更灵活）
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    # ---------- 第 5 步：验证用户存在 ----------
    if user is None:
        # Token 有效但用户已被删除（数据库里找不到）
        # 这在分布式系统中可能发生：Token 还有效但用户被删了
        raise credentials_exception

    return user


# =============================================================================
# 第 3 步：获取当前登录用户（可选认证）
# =============================================================================

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_async_session)
) -> Optional[User]:
    """
    可选的用户认证（允许匿名访问的接口）

    ==========================================================================
    与 get_current_user 的区别：
      - 没有 Token 时不会报错，返回 None
      - 适用于"登录用户有额外功能，匿名用户也能访问"的场景

    典型场景：
      - 查看文章列表：匿名用户可以看，登录用户能看到自己的草稿
      - 搜索内容：匿名可以搜，登录用户能看到搜索历史
      - 获取推荐：匿名有默认推荐，登录用户有个性化推荐

    工作流程：
      1. 尝试从请求头获取 Token（auto_error=False，不会报错）
      2. 如果没有 Token 或 Token 无效，返回 None
      3. 如果有有效 Token，返回对应的 User 对象
    ==========================================================================
    """
    # 没有 Token 的情况（直接返回 None）
    if credentials is None:
        return None

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    # 查询用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
