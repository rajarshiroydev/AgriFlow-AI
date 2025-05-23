# Pydantic settings (reads .env)

# SYNGENTA_AI_AGENT/config/settings.py
import os
import logging
from pydantic import Field, PostgresDsn, AmqpDsn, RedisDsn # Removed MongoDsn for now
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional # Added Optional

logger = logging.getLogger(__name__)

