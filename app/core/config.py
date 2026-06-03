"""
应用配置模块
=============================================================================
职责说明：
  这个模块负责集中管理整个后端服务的所有配置参数。
  所有配置项都从 .env 环境变量文件读取，这样敏感信息（如密码、密钥）
  就不用硬编码在代码里，方便在不同环境（开发、测试、生产）切换配置。

核心设计：
  1. 使用 pydantic-settings 库，它能自动读取 .env 文件并验证类型
  2. Settings 类定义所有配置项及其默认值，运行时会从 .env 覆盖
  3. get_settings() 使用 lru_cache 装饰器实现单例模式，避免重复读取配置
  4. settings 是一个全局实例，整个项目通过它获取配置值

典型场景：
  - 修改 JWT 过期时间：改 .env 中的 JWT_EXPIRE_MINUTES
  - 切换数据库：改 .env 中的 DATABASE_URL
  - 开启调试模式：改 .env 中的 DEBUG=true
=============================================================================
"""
from functools import lru_cache
from typing import Literal

# pydantic-settings 是 pydantic 的扩展，专门用于从环境变量读取配置
# BaseSettings 提供默认值和自动类型转换
# SettingsConfigDict 控制配置如何读取（如 .env 文件路径、编码等）
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    ==========================================================================
    每个字段对应一个配置项，有默认值，可以被 .env 文件中的值覆盖。

    字段命名规范：
      - 布尔字段用 is_ / enable_ 前缀（如 is_debug）
      - 超时字段用 _timeout 后缀
      - URL 字段用 _url 后缀
      - 目录路径用 _dir 后缀

    典型场景示例：
      - app_name: "AI内容运营助手" — 浏览器 tab 显示的名字
      - database_url: 连接 PostgreSQL 的异步驱动 URL
      - log_level: "INFO" — 控制哪些日志会输出
    ==========================================================================
    """

    # 配置项：告诉 pydantic-settings 去哪里找环境变量文件
    # env_file=".env" 表示在项目根目录查找 .env 文件
    # env_file_encoding="utf-8" 确保中文配置能正确读取
    # extra="ignore" 表示 .env 中有多余的字段时忽略，不报错
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --------------------------------------------------------------------------
    # 基础应用配置
    # --------------------------------------------------------------------------
    # 应用名称，用于浏览器 tab 标题、文档页面标题等展示场景
    # 典型值："AI内容运营助手"
    app_name: str = "AI内容运营助手"

    # 调试模式开关
    # - True：开启，SQLAlchemy 会打印所有 SQL 语句，方便开发调试
    # - False：关闭，SQL 静默执行，减少日志噪音
    debug: bool = True

    # --------------------------------------------------------------------------
    # 数据库配置（SQLAlchemy AsyncIO）
    # --------------------------------------------------------------------------
    # 异步数据库连接 URL，格式：数据库类型+驱动://用户名:密码@主机:端口/数据库名
    # 典型场景：
    #   - 本地开发：postgresql+asyncpg://postgres:password@localhost:5432/aicontent
    #   - 生产环境：改成对应的服务器地址和强密码
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/aicontent"

    # PostgreSQL 直连 URL（用于 psycopg3 / LangGraph Checkpointer）
    # 与 database_url 区别：这是同步驱动用的，Checkpointer 需要同步连接
    # 典型场景：LangGraph 需要在数据库里保存工作流状态快照
    postgres_uri: str = "postgresql://postgres:password@localhost:5432/aicontent"

    # --------------------------------------------------------------------------
    # 日志配置
    # --------------------------------------------------------------------------
    # 日志输出级别，控制哪些级别的日志会被记录
    # 级别从低到高：DEBUG < INFO < WARNING < ERROR
    # 典型场景：
    #   - DEBUG：开发时看到所有细节，包括 SQL 语句、变量值
    #   - INFO：生产环境只看重要事件（启动、请求、错误）
    #   - WARNING：只显示潜在问题
    #   - ERROR：只显示真正出错的地方
    log_level: str = "INFO"

    # 日志输出目标，决定日志写到哪儿
    # 典型场景：
    #   - "file"：写到本地文件（默认，开发和大多数生产场景）
    #   - "loki"：发送到 Grafana Loki（需要额外配置）
    #   - "aliyun"：发送到阿里云日志服务
    #   - "volcengine"：发送到字节火山引擎日志服务
    # 注意：目前代码只实现了 "file"，云服务是预留扩展口
    log_target: Literal["file", "loki", "aliyun", "volcengine"] = "file"

    # 日志文件存放目录，相对于项目根目录
    # 典型场景：设为 "logs"，日志会保存在 ./logs/app.log
    log_dir: str = "logs"

    # 是否在控制台输出 JSON 格式日志（文件始终是 JSON，此选项只影响控制台）
    # 典型场景：
    #   - True：JSON 格式，便于日志收集系统解析（如 ELK 栈）
    #   - False：人类可读的彩色文本，方便本地开发看
    log_json: bool = False

    # 是否在控制台输出日志（独立于 log_target 的文件输出）
    # 典型场景：
    #   - True：同时输出到终端，方便实时查看（开发时建议开启）
    #   - False：只写文件，终端保持干净
    log_console: bool = True

    # 是否启用 PII（个人身份信息）脱敏
    # 典型场景：
    #   - True：日志中的邮箱、手机号、身份证号等会被打码，防止敏感信息泄露
    #   - 生产环境强烈建议开启
    log_pii_anonymize: bool = True

    # --------------------------------------------------------------------------
    # JWT 认证配置
    # --------------------------------------------------------------------------
    # JWT 签名密钥，用于给 Token 签名防止篡改
    # 典型场景：
    #   - 开发默认值：随便写一个字符串
    #   - 生产环境：必须改成随机生成的强密钥（至少 32 位），不能泄漏
    # 安全提示：这个密钥如果泄露，攻击者可以伪造任意用户的登录 Token
    jwt_secret_key: str = "your-super-secret-key-change-in-production-2024"

    # JWT 签名算法，HS256 是最常用的对称签名算法（密钥同时用于签名和验签）
    # 典型场景：一般不需要改，HS256 已经足够安全
    jwt_algorithm: str = "HS256"

    # JWT Token 过期时间（分钟）
    # 典型场景：
    #   - 1440 分钟 = 24 小时，用户登录后一天需要重新登录
    #   - 短一些更安全（如 30 分钟），但用户体验会受影响
    #   - 可以配合 refresh token 实现续期
    jwt_expire_minutes: int = 1440  # 24小时

    # --------------------------------------------------------------------------
    # 属性方法
    # --------------------------------------------------------------------------

    @property
    def async_database_url(self) -> str:
        """
        获取异步数据库 URL
        ==========================================================================
        用途说明：
          SQLAlchemy 的异步驱动（asyncpg）需要用 postgresql+asyncpg:// 前缀，
          这个属性返回正确的异步连接字符串。

        典型场景：
          engine = create_async_engine(settings.async_database_url)
        ==========================================================================
        """
        return self.database_url


# =============================================================================
# 配置单例
# =============================================================================

@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例
    ==========================================================================
    工作原理：
      lru_cache 装饰器确保整个进程生命周期内 Settings 只被实例化一次。
      第一次调用时创建 Settings() 并缓存，之后所有调用直接返回缓存。

    典型场景：
      from app.core.config import get_settings
      settings = get_settings()
      print(settings.app_name)
    ==========================================================================
    """
    return Settings()


# 全局配置实例，供其他模块直接导入使用（不用每次调用 get_settings()）
# 注意：直接导入这个实例意味着配置在首次导入时就被锁定了
# 如果需要支持热重载配置，改用 get_settings() 函数
settings = get_settings()
