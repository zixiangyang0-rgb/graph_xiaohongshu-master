"""
LangGraph 工具函数模块
=============================================================================
提供 LangGraph 工作流运行所需的工具函数，其中最重要的是 Checkpointer 的管理。

核心概念：
  - Checkpointer：状态持久化器，把工作流状态保存到数据库
  - AsyncPostgresSaver：PostgreSQL 版本的 Checkpointer
  - Connection Pool：数据库连接池，管理数据库连接的复用

为什么需要 Checkpointer？
  工作流可能在中途中断（用户关闭页面、服务重启等）
  Checkpointer 把状态保存到数据库，下次可以无缝继续
  没有 Checkpointer，每次中断都要从头开始

日常场景：
  1. 服务启动 -> setup_checkpointer() -> 初始化连接池，创建表
  2. 用户执行工作流 -> graph.ainvoke() -> 状态自动持久化
  3. 服务关闭 -> close_checkpointer() -> 关闭连接池
=============================================================================
"""
import asyncio
import selectors
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from typing import Union

from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings


# =============================================================================
# 全局变量
# =============================================================================

# Checkpointer 单例（延迟初始化）
_checkpointer: Union[AsyncPostgresSaver, None] = None

# PostgreSQL 连接池单例
_connection_pool: Union[AsyncConnectionPool, None] = None


# =============================================================================
# 第 1 步：初始化 Checkpointer
# =============================================================================

async def setup_checkpointer() -> BaseCheckpointSaver:
    """
    设置并初始化 Checkpointer（PostgreSQL 持久化）

    ==========================================================================
    工作流程：

    ---------- 第 1 步：检查是否已初始化 ----------
    如果 _checkpointer 已有值，说明之前已经初始化过了，直接返回
    避免重复初始化（连接池重复打开会报错）

    ---------- 第 2 步：创建 Checkpointer 表 ----------
    使用 autocommit 模式连接数据库
    因为 CREATE INDEX CONCURRENTLY 不能在事务块中运行

    AsyncPostgresSaver.setup() 会：
    1. 创建 checkpoints 表（存储状态快照）
    2. 创建 checkpoint_blobs 表（存储大型二进制数据）
    3. 创建 checkpoint_writes 表（存储待写入数据）
    4. 创建 checkpoint_migrations 表（记录迁移版本）

    ---------- 第 3 步：创建连接池 ----------
    AsyncConnectionPool：
    - conninfo：PostgreSQL 连接字符串
    - min_size=1：最小 1 个连接
    - max_size=10：最多 10 个连接
    - open=False：稍后手动打开（避免在 __init__ 中阻塞）

    ---------- 第 4 步：创建 Checkpointer ----------
    AsyncPostgresSaver(_connection_pool)
    这个 Checkpointer 会在每次工作流状态变化时自动持久化

    典型场景：
      服务启动时调用 -> logs "[OK] PostgreSQL Checkpointer initialized - data will persist"
    """
    global _checkpointer, _connection_pool

    # ---------- 第 1 步：检查是否已初始化 ----------
    if _checkpointer is not None:
        return _checkpointer

    # ---------- 第 2 步：创建 Checkpointer 表 ----------
    print(f"[Checkpointer] Connecting to PostgreSQL: {settings.postgres_uri.split('@')[-1]}")

    # 使用 autocommit 模式（setup 中的某些 SQL 不能在事务中运行）
    async with await psycopg.AsyncConnection.connect(
        settings.postgres_uri,
        autocommit=True
    ) as setup_conn:
        # 创建临时 Checkpointer 用于调用 setup()
        temp_checkpointer = AsyncPostgresSaver(setup_conn)
        await temp_checkpointer.setup()
        print("[OK] Checkpointer tables created/verified")

    # ---------- 第 3 步：创建连接池 ----------
    _connection_pool = AsyncConnectionPool(
        conninfo=settings.postgres_uri,
        min_size=1,
        max_size=10,
        open=False,  # 稍后手动打开
    )

    # 打开连接池
    await _connection_pool.open()

    # ---------- 第 4 步：创建 Checkpointer ----------
    _checkpointer = AsyncPostgresSaver(_connection_pool)

    print("[OK] PostgreSQL Checkpointer initialized - data will persist")

    return _checkpointer


# =============================================================================
# 第 2 步：获取 Checkpointer
# =============================================================================

async def get_checkpointer() -> BaseCheckpointSaver:
    """
    获取已初始化的 Checkpointer 实例

    ==========================================================================
    用途：
      工作流编译时需要 Checkpointer
      get_graph() 调用这个函数获取 Checkpointer

    工作流程：
      1. 如果已初始化（_checkpointer 有值），直接返回
      2. 如果未初始化，调用 setup_checkpointer() 初始化

    典型场景：
      compiled_graph = workflow.compile(checkpointer=await get_checkpointer())
    """
    global _checkpointer

    if _checkpointer is None:
        return await setup_checkpointer()

    return _checkpointer


# =============================================================================
# 第 3 步：关闭 Checkpointer
# =============================================================================

async def close_checkpointer() -> None:
    """
    关闭 Checkpointer 和连接池

    ==========================================================================
    用途：
      服务关闭时调用，释放数据库连接资源

    工作流程：
      1. 关闭连接池（_connection_pool.close()）
      2. 清空全局变量（_checkpointer = None）

    为什么重要？
      - 不关闭连接池，数据库连接会保持打开
      - 频繁重启会积累大量 TIME_WAIT 连接
      - 生产环境可能耗尽数据库最大连接数

    典型场景：
      服务关闭时 -> logs "[Checkpointer] PostgreSQL connection pool closed"
    """
    global _checkpointer, _connection_pool

    if _connection_pool is not None:
        # 关闭 PostgreSQL 连接池
        await _connection_pool.close()
        _connection_pool = None
        print("[Checkpointer] PostgreSQL connection pool closed")

    _checkpointer = None
    print("[Checkpointer] Cleaned up")
