"""
================================================================================
数据库 ORM 模型模块（app/models）
================================================================================

职责说明：
  定义 SQLAlchemy ORM 模型，与 PostgreSQL 数据库表一一对应。

模块内容：
  - user.py：User 模型（id, username, password_hash, created_at, updated_at）

模型与表的关系：
  - User 表 → app/models/user.py → SQLAlchemy User 类
  - LangGraph checkpoints 表 → scripts/init_db.sql（原生 SQL，非 ORM）

典型使用场景：
  - 用户注册：创建新的 User 记录，密码使用 argon2 哈希存储
  - 用户登录：根据 username 查找用户，验证密码哈希
  - 依赖注入：在 FastAPI 路由中通过 get_current_user 获取当前登录用户

数据库迁移说明：
  - 当前使用 init_db.sql 手动创建表
  - 将来可考虑使用 Alembic 进行数据库迁移管理
================================================================================
"""

from app.models.user import User

__all__ = ["User"]
