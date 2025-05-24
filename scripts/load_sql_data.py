# Script to load CSV into PostgreSQL
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging
import os
import re

# Important: Import settings AFTER potentially setting a script-specific env var
# if you need to switch DATABASE_URL for local script execution.
# For now, we assume this script might be run from within a Docker container
# or locally with DATABASE_URL in .env pointing to localhost for the DB.
try:
    from config.settings import settings
    DATABASE_URL = str(settings.DATABASE_URL) # Ensure it's a string
except ImportError:
    # Fallback for running script standalone without full app context (less ideal)
    # Requires .env to be in the same dir or parent of script, or manually set
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
    DATABASE_URL = os.getenv("DATABASE_URL_LOCAL") # Use local if defined, else the docker one
    if not DATABASE_URL:
        DATABASE_URL = os.getenv("DATABASE_URL")
        
