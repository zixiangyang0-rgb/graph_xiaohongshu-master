"""
用户表对应的 SQLAlchemy 模型。

这里只放用户最基础的字段：用户名、密码哈希、创建时间、更新时间。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base


class User(Base):
    """
用户表模型。

一条记录就是一个用户账号，密码这里存的是哈希，不会存明文。
"""
    __tablename__ = "users"

    # 主键：UUID 类型，PostgreSQL 原生支持，Python 侧映射为 uuid.UUID 对象
    # default=uuid.uuid4：插入时自动生成 UUID，无需手动指定
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 用户名：最大 50 字符，唯一约束，数据库层面强制不允许重复
    # nullable=False：不允许为空
    # index=True：创建索引，加速按用户名查询（登录时频繁用到）
    username = Column(String(50), unique=True, nullable=False, index=True)

    # 密码哈希：存储 argon2 哈希后的密码，约 60-80 字符，留 255 足够
    # 注意：存的是哈希，不是明文密码
    password_hash = Column(String(255), nullable=False)

    # 时间戳：带时区的时间戳
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
