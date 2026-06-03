"""
安全模块 - JWT 认证与密码处理
=============================================================================
职责说明：
  这个模块提供用户身份认证相关的核心安全功能：
  1. 密码哈希：安全存储用户密码（永远不明文保存）
  2. 密码验证：验证用户登录时输入的密码是否正确
  3. JWT Token：生成和验证登录令牌

安全原理：
  - 密码用 argon2 算法哈希后存储，即使数据库泄露，攻击者也拿不到原始密码
  - JWT Token 包含用户身份信息，服务器用密钥验签后信任，无需查库

典型场景：
  - 用户注册：把明文密码哈希后存数据库
  - 用户登录：验证哈希后的密码，生成 JWT 返回给客户端
  - 受保护接口：客户端带上 JWT，服务器验签后确认身份
=============================================================================
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# jose 库提供 JWT（JSON Web Token）的创建和验证功能
# JWTError：JWT 相关异常（如过期、签名错误）
# jwt：JWT 操作主对象
from jose import JWTError, jwt

# passlib 是密码哈希库，提供多种哈希算法
# CryptContext 管理密码哈希策略，deprecate="auto" 自动废弃不安全的旧哈希
# 使用 argon2 算法（当前最安全的密码哈希算法之一，无长度限制）
# bcrypt 作为备用（兼容旧系统）
from passlib.context import CryptContext

# 导入全局配置获取密钥和算法配置
from app.core.config import settings


# =============================================================================
# 第 1 步：初始化密码哈希上下文
# =============================================================================
# CryptContext 是密码哈希管理器
# schemes=["argon2", "bcrypt"] 指定支持的算法，按顺序优先使用 argon2
# deprecated="auto" 自动废弃那些用旧算法哈希的密码（下次登录时自动升级）
#
# 为什么用 argon2？
#   argon2 是 2015 年密码哈希竞赛冠军，专门设计来抵御 GPU 并行破解和侧信道攻击
#   相比 bcrypt，argon2 的内存消耗可配置，不容易用 GPU 大规模并行破解
#   argon2 无密码长度限制，bcrypt 超过 72 字符会被截断
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


# =============================================================================
# 第 2 步：密码哈希函数
# =============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确
    ==========================================================================
    工作原理：
      将用户输入的明文密码用同样的算法哈希，然后和数据库里存储的哈希比对。
      因为哈希是单向的（不能反推），只能用相同输入产生相同输出来验证。

    参数说明：
      - plain_password：用户登录时输入的明文密码
      - hashed_password：数据库里存储的哈希后的密码

    返回值：
      - True：密码正确（明文哈希后等于存储的哈希）
      - False：密码错误

    为什么不用明文比对？
      1. 数据库泄露时攻击者直接拿到所有密码
      2. 用户可能在多个网站使用相同密码，明文存储会泄漏其他网站账号
      3. 哈希+盐（salt）后，即使用户密码相同，哈希值也不同（防止彩虹表攻击）

    典型场景：
      用户在登录页面输入密码，点击登录
      后端从数据库取出密码哈希，调用 verify_password 比对
      比对成功：生成 JWT Token，允许登录
      比对失败：返回"用户名或密码错误"（不告诉用户是哪个错了）
    ==========================================================================
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    生成密码哈希
    ==========================================================================
    工作原理：
      1. 自动生成随机盐值（salt），防止相同密码产生相同哈希
      2. 用 argon2 算法对"密码+盐"进行哈希运算
      3. 返回格式：$argon2id$v=19$m=19456,t=2,p=1$盐值$哈希值

    参数说明：
      - password：用户注册时输入的明文密码

    返回值：
      - 哈希后的密码字符串，用于存入数据库

    安全设计：
      - 盐值自动生成，每次哈希相同密码会产生不同的哈希值
      - 计算成本高（可配置迭代次数），暴力破解需要大量算力
      - 即使两个用户密码相同，存储的哈希也不同

    典型场景：
      用户注册时，前端把密码 POST 到 /auth/register
      后端调用 get_password_hash() 生成哈希，存入数据库
      数据库里存的是哈希，不是明文

    安全注意：
      - 不要自己实现哈希算法，用这个库已经验证过的实现
      - 不要截断密码，argon2 没有 72 字符限制
      - 不要复用盐值，库自动处理
    ==========================================================================
    """
    return pwd_context.hash(password)


# =============================================================================
# 第 3 步：JWT Token 管理
# =============================================================================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT access token
    ==========================================================================
    工作原理：
      1. 准备载荷（payload）：把用户数据复制一份，加上过期时间
      2. 签名：用 jwt_secret_key 和算法对载荷进行数字签名
      3. 编码：将签名后的结果编码成字符串（URL-safe base64）

    参数说明：
      - data：需要编码进 Token 的数据，通常包含 "sub": user_id
        典型值：{"sub": "user-uuid-123"}
        "sub" 是 JWT 标准字段，表示"主题"（subject），通常放用户 ID
      - expires_delta：自定义过期时间，不传则使用配置文件中的默认值（24小时）

    返回值：
      - JWT Token 字符串，格式：xxxxx.yyyyy.zzzzz
        第一段（xxxxx）：Header，声明算法和类型
        第二段（yyyyy）：Payload，包含用户数据和过期时间
        第三段（zzzzz）：Signature，签名，防篡改

    JWT 安全设计：
      - 签名防篡改：攻击者修改 Payload 内容，签名验证会失败
      - 过期时间：Token 不会永久有效，过期后需要重新登录
      - 密钥保密：只有服务器知道密钥，能生成和验证 Token

    典型场景：
      用户登录成功，后端生成 Token 返回给前端
      前端把 Token 存在 localStorage，每次请求带上 Authorization: Bearer <token>
      服务器验签后，从 Token 中取出 user_id，确认用户身份

    JWT 结构示例：
      {"sub": "abc-123", "exp": 1735689600}
      用 HS256 算法 + 密钥签名后，变成：
      "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMtMTIzIiwiZXhwIjoxNzM1Njg5NjAwfQ.signature"
    ==========================================================================
    """
    # 第 1 步：复制数据，避免修改原始字典
    to_encode = data.copy()

    # 第 2 步：计算过期时间
    if expires_delta:
        # 有自定义过期时间：用当前时间 + delta
        expire = datetime.utcnow() + expires_delta
    else:
        # 用配置默认值：当前时间 + 配置的分钟数
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)

    # 第 3 步：把过期时间加入载荷
    # "exp" 是 JWT 标准声明字段，验证时会自动检查
    to_encode.update({"exp": expire})

    # 第 4 步：签名并编码成 Token 字符串
    # jwt.encode(载荷字典, 密钥, 算法)
    # 算法用 HS256：先用密钥对载荷做 HMAC-SHA256 签名
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码并验证 JWT token
    ==========================================================================
    工作原理：
      1. 接收 Token 字符串，分成三段
      2. 用密钥和算法重新计算签名
      3. 比对计算出的签名和 Token 中的签名是否一致
      4. 检查过期时间（exp）
      5. 返回载荷内容

    参数说明：
      - token：客户端传来的 JWT 字符串

    返回值：
      - 成功：载荷字典（如 {"sub": "user-123", "exp": 1234567890}）
      - 失败：None（Token 无效、过期、签名错误）

    为什么返回 None 而不是抛异常？
      简化调用方处理，不需要 try/except
      调用方自己判断 None 的情况（如返回 401）

    典型场景：
      用户访问受保护接口，带上 Authorization: Bearer <token>
      后端调用 decode_access_token() 验证
      - 验证成功：从 payload["sub"] 取出 user_id，查数据库确认用户存在
      - 验证失败：返回 401 Unauthorized
    ==========================================================================
    """
    try:
        # jwt.decode() 完成所有验证工作：签名、过期时间
        # algorithms 参数限制只接受指定的算法（防止算法替换攻击）
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        # Token 无效的几种情况：
        # - 签名不匹配（Token 被篡改或密钥不对）
        # - Token 已过期（exp 时间已到）
        # - Token 格式不正确
        return None
