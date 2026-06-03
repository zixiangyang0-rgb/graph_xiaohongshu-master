"""
数据库连接模块
=============================================================================
职责说明：
  这个模块负责建立和管理与 PostgreSQL 数据库的连接。

核心设计：
  1. 使用 SQLAlchemy 2.0 的异步引擎（AsyncEngine）实现非阻塞数据库操作
     - 对于 FastAPI 这种异步 Web 框架，异步数据库操作可以同时处理大量请求
     - 不需要为每个请求单独开数据库连接，连接池统一管理复用
  2. create_async_engine() 创建异步引擎，配置连接池参数
  3. async_sessionmaker() 创建会话工厂，每次需要操作数据库时从这里拿会话
  4. declarative_base() 创建 ORM 基类，所有数据库表模型继承它

典型场景：
  - 启动服务：engine.connect() 建立连接，init_db() 创建表
  - 处理请求：在依赖注入中 get_async_session() 获取会话，操作完自动提交
  - 关闭服务：dispose() 关闭所有连接，释放资源

PostgreSQL 连接参数说明：
  - pool_size=5：正常情况下保持 5 个连接备用（适合小规模服务）
  - max_overflow=10：高峰时可以额外创建 10 个连接（总共最多 15 个）
  - pool_pre_ping=True：每次使用连接前先 ping 一下，确保连接没断掉
  - echo=settings.debug：DEBUG 模式下打印 SQL 语句
=============================================================================
"""
from typing import AsyncGenerator

# SQLAlchemy 异步扩展，提供 AsyncEngine、AsyncSession 等异步数据库操作类
# AsyncEngine：异步数据库引擎，负责管理连接池和 SQL 执行
# create_async_engine：创建异步引擎的工厂函数
# async_sessionmaker：创建会话工厂，从连接池拿连接创建会话
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
# declarative_base：创建 ORM 基类，继承它可以定义 Python 风格的数据库表模型
# 例如：class User(Base) -> 自动映射到 users 表
from sqlalchemy.orm import declarative_base

# 导入全局配置实例，获取数据库连接 URL
from app.core.config import settings


# =============================================================================
# 第 1 步：创建异步数据库引擎
# =============================================================================
# create_async_engine() 是 SQLAlchemy 提供创建异步引擎的工厂函数
# 参数说明：
#   - settings.async_database_url：异步连接 URL（postgresql+asyncpg://...）
#     典型值："postgresql+asyncpg://postgres:password@localhost:5432/aicontent"
#   - echo=settings.debug：开启后会在控制台打印所有执行的 SQL 语句
#     开发时 True（看 SQL 长啥样），生产环境设为 False
#   - pool_pre_ping=True：每次从连接池拿连接前，先发送一个小命令测试连接是否有效
#     防止从连接池拿到一个已经断开的连接（数据库服务器有连接超时）
#   - pool_size=5：连接池"常驻"连接数量，同时供 5 个请求使用
#     小型服务 5 个足够，大型服务可以调到 20-50
#   - max_overflow=10：当 5 个连接不够用时（都在处理请求），最多额外创建 10 个临时连接
#     总并发上限 = pool_size + max_overflow = 5 + 10 = 15 个同时请求
#     请求完成后临时连接立即释放，不占用池
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


# =============================================================================
# 第 2 步：创建异步会话工厂
# =============================================================================
# 为什么要工厂？直接用 engine.session() 不行吗？
#   工厂模式可以预先配置会话的默认行为，更灵活
# 参数说明：
#   - bind=engine：绑定到刚才创建的引擎，会话自动使用这个引擎拿连接
#   - class_=AsyncSession：指定会话类，必须是异步会话
#   - expire_on_commit=False：提交后不自动过期对象
#     如果设为 True，提交后访问对象属性会重新查数据库（懒加载）
#     设为 False 性能更好，但要注意访问的对象引用可能在提交后失效
#   - autocommit=False：默认不自动提交，必须显式调用 commit()
#     这样可以确保一组 SQL 操作要么全部成功，要么全部回滚
#   - autoflush=False：关闭自动刷新，手动控制何时将修改写入数据库
#     设为 True 时，每次查询前会自动先提交 pending 的修改
#     关闭后更精确控制事务边界
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# =============================================================================
# 第 3 步：创建 ORM 基类
# =============================================================================
# declarative_base() 是 SQLAlchemy 的声明式 ORM 基类
# 所有数据库表模型（如 User、Article）都要继承 Base
# 继承后，SQLAlchemy 会自动：
#   - 把类名映射到表名（User -> users，Article -> articles）
#   - 把类属性映射到表列
#   - 提供 add()、query() 等 ORM 操作方法
Base = declarative_base()


# =============================================================================
# 第 4 步：定义依赖注入函数（FastAPI 专用）
# =============================================================================

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（FastAPI 依赖注入）
    ==========================================================================
    使用方式：
      在 FastAPI 路由函数参数中使用：async def get_user(db: AsyncSession = Depends(get_async_session))

    工作流程（每一步都有明确目的）：
      第 1 步：async with async_session_factory() as session
                从连接池取出一个空闲连接，创建会话
                with 块确保会话在异常情况下也能正确清理
      第 2 步：yield session
                把会话交给路由处理函数使用
                在 yield 之前，会话已经处于事务中
      第 3 步：try 块正常路径：await session.commit()
                提交事务，所有在 session 中做的增删改操作全部写入数据库
      第 4 步：except 块异常路径：await session.rollback()
                回滚事务，撤销所有未提交的修改，保持数据一致性
      第 5 步：finally 块：await session.close()
                关闭会话，将连接归还连接池（不是断开连接）

    为什么要用 try/except/finally？
      - commit() 可能在写入时出错，如果不在 except 中 rollback，连接会被"污染"
      - finally 确保无论成功还是失败，连接都能正确归还池
      - 防止连接泄漏：泄漏的连接最终耗尽连接池，导致所有请求卡住

    典型场景：
      @app.get("/users/{user_id}")
      async def get_user(user_id: int, db: AsyncSession = Depends(get_async_session)):
          # db 就是这里 yield 出去的会话
          result = await db.execute(select(User).where(User.id == user_id))
          user = result.scalar_one_or_none()
          return user
    ==========================================================================
    """
    # 从会话工厂获取会话（从连接池拿连接）
    async with async_session_factory() as session:
        try:
            # yield 之前已经开启事务了，yield 把 session 交给调用者
            yield session
            # 正常结束：提交事务，把修改写入数据库
            await session.commit()
        except Exception:
            # 出错了：回滚事务，撤销所有未提交的修改
            await session.rollback()
            # 重新抛出异常，让 FastAPI 的异常处理器捕获（返回 500 错误）
            raise
        finally:
            # 无论成功还是失败，都关闭会话，归还连接到连接池
            await session.close()


# =============================================================================
# 第 5 步：数据库生命周期管理（启动和关闭）
# =============================================================================

async def init_db() -> None:
    """
    初始化数据库（创建所有表）
    ==========================================================================
    调用时机：FastAPI 应用启动时（lifespan startup 阶段）

    工作原理：
      Base.metadata.create_all() 会检查所有继承自 Base 的模型类，
      自动生成 CREATE TABLE 语句并执行（如果表不存在的话）。

    为什么不直接用 SQL？
      ORM 自动检测模型字段变化生成建表 SQL，不用手动写 ALTER TABLE
      适合开发阶段快速迭代，不用操心表结构变更

    注意事项：
      - 只创建不存在的表，不修改已有表的结构
      - 修改表结构（如加列）需要用 Alembic 迁移工具
      - 生产环境建议关闭自动建表，改用正式的数据库迁移流程

    典型场景：
      应用启动时，在控制台打印 "[DB] Database initialized"
      如果失败，说明数据库连接有问题（用户名密码错、数据库不存在等）
    ==========================================================================
    """
    async with engine.begin() as conn:
        # run_sync() 允许在异步上下文中运行同步的 SQLAlchemy 操作
        # Base.metadata.create_all() 是同步的，所以需要 run_sync 包装
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Database initialized")


async def close_db() -> None:
    """
    关闭数据库连接
    ==========================================================================
    调用时机：FastAPI 应用关闭时（lifespan shutdown 阶段）

    工作原理：
      engine.dispose() 关闭数据库引擎，释放所有连接池中的连接。

    为什么重要？
      - 不关闭的话，数据库连接会保持打开状态
      - 如果服务频繁重启，会积累大量 TIME_WAIT 状态的连接
      - 生产环境中可能耗尽数据库的最大连接数限制

    典型场景：
      应用关闭时，打印 "[DB] Database connection closed"
      此时如果还有未完成的请求，会等待它们完成后再执行 dispose
    ==========================================================================
    """
    await engine.dispose()
    print("[DB] Database connection closed")
