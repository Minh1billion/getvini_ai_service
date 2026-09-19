from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DICTIONARIES_DIR = BASE_DIR / "dictionaries"
FONTS_DIR = BASE_DIR / "fonts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    qc_verify_model: str = "openai/gpt-oss-120b"
    qc_llm_seed: int = 7
    qc_llm_max_retries: int = 3
    qc_llm_max_wait_seconds: float = 30
    qc_llm_json_retries: int = 2
    qc_cache_db: str = str(BASE_DIR / "qc_cache.sqlite3")

    qc_llm_context_window: int = 8000
    qc_llm_reserved_output_tokens: int = 1500
    qc_llm_min_scenarios_per_batch: int = 1
    qc_llm_max_scenarios_per_batch: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
