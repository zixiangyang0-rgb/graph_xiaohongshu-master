"""
用户模型
=============================================================================
职责说明：
  定义 users 数据库表的结构，映射到 PostgreSQL 数据库。

核心设计：
  - 继承 SQLAlchemy 的 declarative_base() 创建的 Base
  - 每个类属性对应数据库表的一个列（Column）
  - SQLAlchemy 会自动管理 id、created_at 等字段的生成和更新

典型场景：
  - 用户注册：插入新行到 users 表
  - 用户登录：查询 users 表验证用户名和密码哈希
  - 获取用户信息：从 users 表读取 id、username、created_at
=============================================================================
"""
import uuid
from datetime import datetime

# SQLAlchemy 核心列类型
# String：可变长度字符串，参数指定最大长度
# DateTime：时间戳类型，支持时区
from sqlalchemy import Column, String, DateTime

# PostgreSQL 专有类型
# UUID：PostgreSQL 原生 UUID 类型，Python 侧是 uuid.UUID 对象
from sqlalchemy.dialects.postgresql import UUID

# 导入 ORM 基类（所有模型都要继承它）
# declarative_base() 在 db.py 中创建，继承它之后 SQLAlchemy 才能管理这个表
from app.core.db import Base


class User(Base):
    """
    用户表模型
    ==========================================================================
    映射到 PostgreSQL 的 users 表。

    字段详解（字段含义 + 典型场景）：

    | 字段名          | 类型          | 说明                                          |
    |-----------------|---------------|-----------------------------------------------|
    | id              | UUID          | 用户唯一标识符，自动生成 UUID                  |
    | username        | VARCHAR(50)   | 用户名，唯一约束，用于登录                     |
    | password_hash   | VARCHAR(255)  | 密码哈希，argon2 算法存储                      |
    | created_at      | TIMESTAMPTZ   | 创建时间，INSERT 时自动填充                    |
    | updated_at      | TIMESTAMPTZ   | 更新时间，UPDATE 时自动刷新                    |

    为什么用 UUID 而不是自增整数做主键？
      - UUID 全局唯一，不需要中央发号器
      - 合并数据库时不会冲突
      - 不暴露业务量（竞争对手看不到用户数量）
      - 缺点：存储空间更大（16 字节 vs 4 字节）

    为什么 username 要唯一？
      - 用户用用户名登录，必须保证不重复
      - index=True 创建 B-tree 索引，加速按用户名查询
    ==========================================================================
    """
    # 表名：Python 类名转蛇形命名（User -> users）
    __tablename__ = "users"

    # ---------- 主键 ----------
    # UUID 类型，PostgreSQL 原生支持，Python 侧映射为 uuid.UUID 对象
    # default=uuid.uuid4：插入时自动生成 UUID，无需手动指定
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ---------- 用户名字段 ----------
    # String(50)：最大 50 字符的用户名
    # unique=True：数据库层面强制唯一约束，不允许重复用户名
    # nullable=False：不允许为空，必须提供
    # index=True：创建索引，加速按用户名查询（登录时频繁用到）
    username = Column(String(50), unique=True, nullable=False, index=True)

    # ---------- 密码哈希字段 ----------
    # String(255)：存储 argon2 哈希后的密码
    # 典型 argon2 哈希长度约 60-80 字符，留 255 足够
    # nullable=False：密码必须提供（注册时）
    # 注意：存的是哈希，不是明文密码
    password_hash = Column(String(255), nullable=False)

    # ---------- 时间戳字段 ----------
    # DateTime(timezone=True)：带时区的时间戳
    # default=datetime.utcnow：INSERT 时自动填充当前 UTC 时间
    # onupdate=datetime.utcnow：UPDATE 时自动刷新为当前时间
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        """
        调试友好表示
        ==========================================================================
        当 print(user) 或在调试器中查看对象时，显示友好的格式。
        不暴露 password_hash 等敏感信息。
        """
        return f"<User {self.username}>"
