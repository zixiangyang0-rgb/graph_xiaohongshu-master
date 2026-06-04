#!/usr/bin/env python3
# =============================================================================
# 数据库连接测试脚本
# =============================================================================
#
# 职责说明：
#   验证 Python 能否成功连接到 PostgreSQL 数据库。
#   用于在启动应用之前排查数据库连接问题。
#
# 典型场景：
#   1. 新机器部署时，运行此脚本确认数据库连通性
#   2. 修改 DATABASE_URL 环境变量后，验证新连接字符串是否正确
#   3. 排查 "connection refused"、"authentication failed" 等错误
#
# 使用方法：
#   python test_db_connection.py
#   # 或指定数据库 URL：
#   DATABASE_URL="postgresql+psycopg://postgres:password@localhost:5432/graph_xiaohongshu" python test_db_connection.py
#
# 依赖：psycopg（从 requirements.txt 安装）
# =============================================================================

import os
import sys
from urllib.parse import urlparse

# 从项目根目录的 core 模块导入配置
# get_settings() 读取 .env 中的 DATABASE_URL 环境变量
from app.core.config import get_settings

# psycopg 的连接池，提供异步数据库连接能力
from psycopg import Connection


def test_connection():
    """
    测试 PostgreSQL 数据库连接的核心函数。

    执行步骤：
      1. 获取配置（DATABASE_URL）
      2. 解析连接参数（host, port, dbname, user, password）
      3. 尝试建立连接（使用 psycopg）
      4. 执行简单查询验证连接有效
      5. 输出测试结果
    """
    print("=" * 60)
    print("PostgreSQL 数据库连接测试")
    print("=" * 60)

    settings = get_settings()
    print(f"\n数据库 URL: {settings.database_url}")
    # 第 2 步：直接从 URL 字符串解析连接参数用于显示（不用于连接）
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    print(f"连接参数: host={parsed.hostname}, "
          f"port={parsed.port}, "
          f"dbname={parsed.path.lstrip('/')}")

    # 第 2 步：解析 psycopg 连接参数
    # psycopg 直接接受 libpq 连接字符串格式，无需手动解析
    # 直接使用 settings.postgres_uri（标准字符串格式，用于 psycopg）
    db_url = settings.postgres_uri

    print("\n正在连接数据库...")

    # 第 3 步：建立连接
    # psycopg.connect() 是同步的，如果连接失败会抛出异常
    # 常见异常：
    #   - psycopg.OperationalError: 网络不通、端口拒绝
    #   - psycopg.errors.InvalidCatalogName: 数据库名不存在
    #   - psycopg.errors.InvalidPassword: 密码错误
    try:
        conn = Connection.connect(db_url)
        print("连接成功！")

        # 第 4 步：执行简单查询验证
        # cursor.execute() 执行 SQL
        # cursor.fetchone() 获取一行结果
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"\n数据库版本:\n  {version}")

        # 查询当前连接的数据库名
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print(f"当前数据库: {db_name}")

        # 查询当前用户
        cursor.execute("SELECT current_user;")
        user = cursor.fetchone()[0]
        print(f"当前用户: {user}")

        cursor.close()
        conn.close()
        print("\n连接测试通过！")
        print("=" * 60)
        return True

    # 第 5 步：异常处理
    except Exception as e:
        print(f"\n连接失败！错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("\n排查建议:")
        print("  1. 确认 PostgreSQL 服务已启动")
        print("  2. 检查 DATABASE_URL 环境变量是否正确")
        print("  3. 确认数据库用户权限足够")
        print("  4. 检查防火墙是否允许数据库端口访问")
        print("=" * 60)
        return False


if __name__ == "__main__":
    # 直接运行脚本时执行测试
    # sys.exit(0) 表示成功，sys.exit(1) 表示失败
    success = test_connection()
    sys.exit(0 if success else 1)
