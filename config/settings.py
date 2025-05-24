import os
import logging
from pydantic import Field, PostgresDsn, AmqpDsn, RedisDsn, HttpUrl # Added HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")

    # PostgreSQL for Syngenta Hackathon
    DATABASE_URL: PostgresDsn

    # Celery
    CELERY_BROKER_URL: AmqpDsn
    CELERY_RESULT_BACKEND: RedisDsn

    # Hackathon Specific API details
    SYNGENTA_HACKATHON_API_KEY: str
    SYNGENTA_HACKATHON_API_BASE_URL: HttpUrl # Changed to HttpUrl for validation

    # Optional: If you plan to use OpenAI's GPT-4o for anything *else* directly
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY")

    # App Settings
    APP_BASE_URL: str = "http://localhost:8000" # This is fine for local

    # Vector Store Path
    VECTOR_STORE_PATH: str = "data/processed/vector_store"

    model_config = SettingsConfigDict(
        # Corrected path to ensure it finds .env in the project root
        # Assumes settings.py is in SYNGENTA_AI_AGENT/config/
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False
    )

try:
    settings = Settings()
    logger.info(f"Settings loaded for ENVIRONMENT: {settings.ENVIRONMENT}")
    db_url_log = "PostgreSQL Database URL: Could not parse components"
    if settings.DATABASE_URL:
        
        
        #Just log the string representation, hiding credentials
        url_parts = str(settings.DATABASE_URL).split('@')
        if len(url_parts) > 1:
            db_url_log = f"PostgreSQL Database URL (service/db): {url_parts[-1]}"
        else:
            db_url_log = f"PostgreSQL Database URL: {str(settings.DATABASE_URL)}" # If no @ symbol
    logger.info(db_url_log)
    logger.info(f"Hackathon API Base URL: {settings.SYNGENTA_HACKATHON_API_BASE_URL}")

    if not settings.SYNGENTA_HACKATHON_API_KEY:
        # This should be caught by Pydantic if it's not Optional and has no default
        logger.critical("SYNGENTA_HACKATHON_API_KEY is not set. LLM and Embedding features will fail.")
    # The OPENAI_API_KEY warning is fine as it's Optional
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set. Direct OpenAI GPT-4o calls (if any) will fail.")
    # Removed ANTHROPIC_API_KEY warning as we are using the hackathon API for Claude

except Exception as e:
    logger.critical(f"CRITICAL ERROR loading settings: {e}", exc_info=True)
    raise SystemExit(f"Configuration error: {e}")