import os
import logging
from pydantic import Field, PostgresDsn, AmqpDsn, RedisDsn, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse # Import for robust URL parsing for logging

logger = logging.getLogger(__name__)

# --- Determine project root and .env file path ---
try:
    PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
    ENV_FILE_PATH = PROJECT_ROOT_DIR / ".env"
except NameError: 
    PROJECT_ROOT_DIR = Path.cwd()
    ENV_FILE_PATH = PROJECT_ROOT_DIR / ".env"
    logger.warning(f"__file__ not defined in settings.py, assuming CWD ('{PROJECT_ROOT_DIR}') is project root for .env path.")

# --- Explicitly load .env using python-dotenv BEFORE Pydantic/BaseSettings tries ---
if ENV_FILE_PATH.exists():
    logger.info(f"settings.py: Explicitly loading .env from: {ENV_FILE_PATH}")
    load_dotenv(dotenv_path=ENV_FILE_PATH, override=True) 
else:
    logger.warning(f"settings.py: .env file not found at {ENV_FILE_PATH}. Will rely on Pydantic's loading or system environment variables.")


class Settings(BaseSettings):
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    DATABASE_URL: PostgresDsn # Pydantic handles validation of this
    CELERY_BROKER_URL: AmqpDsn
    CELERY_RESULT_BACKEND: RedisDsn
    SYNGENTA_HACKATHON_API_KEY: str
    SYNGENTA_HACKATHON_API_BASE_URL: HttpUrl
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY")
    APP_BASE_URL: str = "http://localhost:8000"
    VECTOR_STORE_PATH: str = "data/processed/vector_store"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH), # Pydantic also uses this
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False
    )

try:
    settings = Settings()
    logger.info(f"Settings loaded for ENVIRONMENT: {settings.ENVIRONMENT}")

    # Robust logging for DATABASE_URL components
    if settings.DATABASE_URL:
        db_url_str_for_log = str(settings.DATABASE_URL) # Get the string representation
        logger.info(f"settings.py: DATABASE_URL as configured by Pydantic: {db_url_str_for_log}")
        try:
            # Use urllib.parse for reliable component extraction from the string URL for logging
            parsed_for_log = urlparse(db_url_str_for_log)
            host_to_log = parsed_for_log.hostname if parsed_for_log.hostname else "N/A"
            port_to_log = str(parsed_for_log.port) if parsed_for_log.port else "N/A"
            db_name_to_log = parsed_for_log.path.lstrip('/') if parsed_for_log.path else "N/A"
            logger.info(f"settings.py: Effective database host: {host_to_log}, Port: {port_to_log}, DB: {db_name_to_log}")
        except Exception as e_parse_log:
            logger.warning(f"settings.py: Could not parse DATABASE_URL string for detailed logging: {e_parse_log}. URL string was: {db_url_str_for_log}")
    else:
        logger.info("settings.py: DATABASE_URL is NOT SET.")


    logger.info(f"Hackathon API Base URL: {settings.SYNGENTA_HACKATHON_API_BASE_URL}")

    api_key_to_log = "NOT SET"
    if settings.SYNGENTA_HACKATHON_API_KEY:
        if len(settings.SYNGENTA_HACKATHON_API_KEY) > 4:
            api_key_to_log = f"{'*' * (len(settings.SYNGENTA_HACKATHON_API_KEY) - 4)}{settings.SYNGENTA_HACKATHON_API_KEY[-4:]}"
        else:
            api_key_to_log = "**** (key too short to mask properly)"
    logger.info(f"Hackathon API Key (masked): {api_key_to_log}")

    if not settings.SYNGENTA_HACKATHON_API_KEY:
        logger.critical("SYNGENTA_HACKATHON_API_KEY is not set. LLM and Embedding features will fail.")
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set. Direct OpenAI GPT-4o calls (if any) will fail.")

except Exception as e:
    logger.critical(f"CRITICAL ERROR loading settings in settings.py: {e}", exc_info=True)
    logger.error("Settings load failed or encountered an error during logging, but allowing script to continue for debugging (if not a fatal Pydantic error)...")