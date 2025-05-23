# Pydantic settings (reads .env)
import os
import logging
from pydantic import Field, PostgresDsn, AmqpDsn, RedisDsn # Removed MongoDsn for now
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional # Added Optional

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")

    # PostgreSQL for Syngenta Hackathon
    DATABASE_URL: PostgresDsn

    # Celery
    CELERY_BROKER_URL: AmqpDsn
    CELERY_RESULT_BACKEND: RedisDsn

    # LLM API Keys (LangChain typically picks these up from environment if set)
    # You might not need them explicitly here if your LangChain templates handle it.
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY") # For GPT-4o if used directly
    ANTHROPIC_API_KEY: Optional[str] = Field(None, env="ANTHROPIC_API_KEY") # For Claude

    # App Settings
    APP_BASE_URL: str = "http://localhost:8000"

    # Vector Store Path (can be relative to project root)
    VECTOR_STORE_PATH: str = "data/processed/vector_store"


    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'), # Correct path to .env
        env_file_encoding='utf-8',
        extra='ignore', # Allow extra env vars not defined in model
        case_sensitive=False
    )

try:
    settings = Settings()
    logger.info(f"Settings loaded for ENVIRONMENT: {settings.ENVIRONMENT}")
    logger.info(f"PostgreSQL Database URL: {settings.DATABASE_URL}") # Will show user/pass, be careful in public logs
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set. Direct OpenAI calls will fail.")
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set. Claude calls may fail if not handled by templates/other means.")

except Exception as e:
    logger.critical(f"CRITICAL ERROR loading settings: {e}", exc_info=True)
    raise SystemExit(f"Configuration error: {e}")