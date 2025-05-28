# SYNGENTA_AI_AGENT/config/settings.py
import os
import logging
from pydantic import Field, PostgresDsn, AmqpDsn, RedisDsn, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path
# from dotenv import load_dotenv # No longer strictly needed here if Pydantic handles it
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# --- Determine project root and .env file path ---
try:
    PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
    ENV_FILE_PATH = PROJECT_ROOT_DIR / ".env"
except NameError: 
    PROJECT_ROOT_DIR = Path.cwd()
    ENV_FILE_PATH = PROJECT_ROOT_DIR / ".env"
    logger.warning(f"__file__ not defined in settings.py, assuming CWD ('{PROJECT_ROOT_DIR}') is project root for .env path.")

# --- Pydantic will handle .env loading via model_config ---
if ENV_FILE_PATH.exists():
    logger.info(f"settings.py: .env file found at {ENV_FILE_PATH}. Pydantic's BaseSettings will attempt to load it.")
else:
    logger.warning(f"settings.py: .env file not found at {ENV_FILE_PATH}. Relying on system environment variables.")


class Settings(BaseSettings):
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    DATABASE_URL: PostgresDsn
    CELERY_BROKER_URL: AmqpDsn
    CELERY_RESULT_BACKEND: RedisDsn
    SYNGENTA_HACKATHON_API_KEY: str
    SYNGENTA_HACKATHON_API_BASE_URL: HttpUrl
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY")
    APP_BASE_URL: str = "http://localhost:8000"
    VECTOR_STORE_PATH: str = "data/processed/vector_store"

    model_config = SettingsConfigDict(
        # Pydantic will load this .env file if it exists,
        # BUT actual environment variables (like those from docker-compose environment block)
        # will take precedence.
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else None,
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False
    )

try:
    settings = Settings() # Pydantic does its magic here
    logger.info(f"Settings loaded for ENVIRONMENT: {settings.ENVIRONMENT}")

    # Robust logging for DATABASE_URL components
    if settings.DATABASE_URL:
        db_url_str_for_log = str(settings.DATABASE_URL)
        logger.info(f"settings.py: DATABASE_URL as configured by Pydantic: {db_url_str_for_log}")
        try:
            parsed_for_log = urlparse(db_url_str_for_log)
            host_to_log = parsed_for_log.hostname if parsed_for_log.hostname else "N/A"
            port_to_log = str(parsed_for_log.port) if parsed_for_log.port else "N/A"
            db_name_to_log = parsed_for_log.path.lstrip('/') if parsed_for_log.path else "N/A"
            logger.info(f"settings.py: Effective database host: {host_to_log}, Port: {port_to_log}, DB: {db_name_to_log}")
        except Exception as e_parse_log:
            logger.warning(f"settings.py: Could not parse DATABASE_URL string for detailed logging: {e_parse_log}. URL string was: {db_url_str_for_log}")
    else:
        logger.warning("settings.py: DATABASE_URL is NOT SET or could not be loaded.")


    logger.info(f"Hackathon API Base URL: {settings.SYNGENTA_HACKATHON_API_BASE_URL}")
    api_key_to_log = "NOT SET"
    if settings.SYNGENTA_HACKATHON_API_KEY:
        api_key_to_log = f"***{settings.SYNGENTA_HACKATHON_API_KEY[-4:]}" if len(settings.SYNGENTA_HACKATHON_API_KEY) > 4 else "****"
    logger.info(f"Hackathon API Key (masked): {api_key_to_log}")

    if not settings.SYNGENTA_HACKATHON_API_KEY:
        logger.critical("SYNGENTA_HACKATHON_API_KEY is not set. LLM and Embedding features will fail.")
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set. Direct OpenAI GPT-4o calls (if any) will fail.")

except Exception as e:
    logger.critical(f"CRITICAL ERROR loading settings in settings.py: {e}", exc_info=True)
    raise