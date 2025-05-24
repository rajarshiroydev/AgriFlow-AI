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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE_PATH = os.path.join(BASE_DIR, "data", "raw", "DataCoSupplyChainDataset.csv")
TABLE_NAME = "supply_chain_transactions"

def clean_column_name(col_name):
    """Cleans column names to be SQL-friendly: lowercase, underscores, no special chars."""
    col_name = col_name.lower()
    col_name = re.sub(r'\s+', '_', col_name)  # Replace spaces with underscores
    col_name = re.sub(r'[^a-z0-9_]', '', col_name) # Remove non-alphanumeric (except underscore)
    if not col_name: # Handle cases where column name becomes empty
        col_name = "unnamed_col"
    if col_name[0].isdigit(): # Handle column names starting with a digit
        col_name = f"_{col_name}"
    return col_name

def load_data():
    if not os.path.exists(CSV_FILE_PATH):
        logger.error(f"CSV file not found at: {CSV_FILE_PATH}")
        return

    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Cannot connect to PostgreSQL.")
        return

    logger.info(f"Connecting to database: {DATABASE_URL.split('@')[-1]}") # Hide user/pass from log
    engine = None
    try:
        engine = create_engine(DATABASE_URL)
        logger.info(f"Reading CSV file from: {CSV_FILE_PATH}")
        # Read a small chunk first to infer dtypes and clean column names
        try:
            df_sample = pd.read_csv(CSV_FILE_PATH, encoding='latin1', nrows=5) # Try latin1 if utf-8 fails
        except UnicodeDecodeError:
            logger.warning("UTF-8 decoding failed, trying ISO-8859-1 for CSV.")
            df_sample = pd.read_csv(CSV_FILE_PATH, encoding='ISO-8859-1', nrows=5)

        original_columns = df_sample.columns.tolist()
        cleaned_columns = {col: clean_column_name(col) for col in original_columns}
        logger.info(f"Original columns: {original_columns}")
        logger.info(f"Cleaned columns: {list(cleaned_columns.values())}")

        # Read the full CSV in chunks for memory efficiency
        chunk_size = 10000  # Adjust based on your system's memory
        first_chunk = True

        logger.info(f"Starting data load into table '{TABLE_NAME}' in chunks of {chunk_size}...")
        for i, chunk_df in enumerate(pd.read_csv(CSV_FILE_PATH, encoding='ISO-8859-1', chunksize=chunk_size)): # Or latin1
            chunk_df.rename(columns=cleaned_columns, inplace=True)
            
            # Attempt to convert date columns - you MUST identify your date columns
            # Example: Assuming 'order_date_dateorders' and 'shipping_date_dateorders' are date columns
            date_columns_to_convert = ['order_date_dateorders', 'shipping_date_dateorders'] # Add your actual date columns here after cleaning
            for col in date_columns_to_convert:
                if col in chunk_df.columns:
                    try:
                        # Try multiple formats, be careful with dayfirst/monthfirst
                        chunk_df[col] = pd.to_datetime(chunk_df[col], errors='coerce')
                    except Exception as e:
                        logger.warning(f"Could not convert column {col} to datetime in chunk {i}: {e}")
                        chunk_df[col] = None # Or handle as appropriate
                else:
                    logger.warning(f"Expected date column '{col}' not found in chunk {i}.")


            try:
                if_exists_strategy = 'replace' if first_chunk else 'append'
                chunk_df.to_sql(TABLE_NAME, engine, if_exists=if_exists_strategy, index=False, chunksize=1000) # Write chunk to SQL
                logger.info(f"Loaded chunk {i+1} ({len(chunk_df)} rows) to '{TABLE_NAME}'. Strategy: {if_exists_strategy}")
                if first_chunk:
                    first_chunk = False
            except Exception as e:
                logger.error(f"Error loading chunk {i+1} to SQL: {e}")
                logger.error(f"Problematic chunk head:\n{chunk_df.head()}")
                # You might want to save the problematic chunk to a file for inspection
                # chunk_df.to_csv(f"problem_chunk_{i+1}.csv", index=False)
                # Consider whether to stop or continue on error
                # break # Stop on first error
                continue # Skip problematic chunk and continue


        logger.info(f"Data loading process completed for table '{TABLE_NAME}'.")

        # Verify by counting rows
        with engine.connect() as connection:
            result = connection.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}"))
            count = result.scalar_one()
            logger.info(f"Table '{TABLE_NAME}' now contains {count} rows.")

    except SQLAlchemyError as e:
        logger.error(f"Database error during data loading: {e}", exc_info=True)
    except FileNotFoundError:
        logger.error(f"ERROR: CSV file not found at {CSV_FILE_PATH}")
    except UnicodeDecodeError as e:
        logger.error(f"Unicode decoding error reading CSV. Try specifying encoding (e.g., 'latin1' or 'ISO-8859-1'). Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        if engine:
            engine.dispose()
            logger.info("Database engine disposed.")

if __name__ == "__main__":
    load_data()