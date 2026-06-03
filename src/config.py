"""Centralized configuration loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM: DeepSeek (OpenAI-compatible) ----
    deepseek_api_key: SecretStr
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ---- Embedding: 通义 DashScope (OpenAI-compatible) ----
    dashscope_api_key: SecretStr
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_embed_model: str = "text-embedding-v3"

    # ---- Vector store ----
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "enterprise_docs"

    # ---- Retrieval / generation knobs ----
    retrieve_top_k: int = 5
    max_reflect_rounds: int = 2

    # ---- Networking ----
    request_timeout: int = 60   # 单次 API 调用超时（秒），防止挂起死等

    # ---- Observability (optional) ----
    langsmith_tracing: bool = False
    langsmith_api_key: Optional[SecretStr] = None
    langsmith_project: str = "enterprise-doc-agent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
