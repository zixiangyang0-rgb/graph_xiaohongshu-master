"""
从 .env 文件读取所有后端配置。
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类，每个字段会被 .env 中的同名值覆盖。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 基础
    app_name: str = "AI内容运营助手"
    debug: bool = True

    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/aicontent"
    postgres_uri: str = "postgresql://postgres:password@localhost:5432/aicontent"
    async_database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/aicontent"

    # JWT
    jwt_secret: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 1 天

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_model: str = "doubao-seed-1-8-251228"
    llm_model_fast: str = "doubao-seed-1-6-flash-250828"
    llm_temperature: float = 0.7
    llm_temperature_fast: float = 0.7
    llm_temperature_extract: float = 0.4

    # 画图
    ark_api_key: str = ""

    # 日志
    log_level: str = "INFO"
    log_target: str = "both"
    log_dir: str = "logs"
    log_json: bool = True
    log_console: bool = True
    log_pii_anonymize: bool = True


@lru_cache()
def get_settings() -> Settings:
    """单例：同一进程里只读一次配置。"""
    return Settings()
