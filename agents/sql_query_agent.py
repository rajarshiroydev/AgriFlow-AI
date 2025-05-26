# 
# SYNGENTA_AI_AGENT/agents/sql_query_agent.py
import os
import logging
from typing import Any, Dict, List

from sqlalchemy import create_engine

from langchain_community.utilities import SQLDatabase # For wrapping the DB
from langchain.agents import create_sql_agent # The agent toolkit
from langchain_community.agent_toolkits import SQLDatabaseToolkit # Provides tools for the agent
# Note: Depending on your LangChain version, create_sql_agent might be directly in langchain.agents
# or you might use a different SQL chain like SQLDatabaseChain directly.
# For now, let's aim for create_sql_agent as it's quite powerful.

from core.hackathon_llms import SyngentaHackathonLLM # Your custom LLM
from config.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize LLM for SQL Agent ---
sql_generation_llm = None
try:
    sql_generation_llm = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", # Sonnet is good for SQL generation
        temperature=0.1,             # Lower temperature for more deterministic SQL
        max_tokens=2000              # Allow for potentially complex SQL + explanations
    )
    logger.info("SyngentaHackathonLLM (Claude 3.5 Sonnet) initialized for SQL Agent.")
except Exception as e:
    logger.error(f"Failed to initialize sql_generation_llm: {e}", exc_info=True)

# --- Initialize Database Connection ---
db_engine = None
db = None
if settings.DATABASE_URL:
    try:
        db_engine = create_engine(str(settings.DATABASE_URL)) # Ensure URL is string
        db = SQLDatabase(db_engine)
        logger.info(f"SQLDatabase initialized for PostgreSQL. Dialect: {db.dialect}")
        # You can test the connection or list tables here if needed
        # logger.info(f"Sample tables: {db.get_usable_table_names()[:5]}")
    except Exception as e:
        logger.error(f"Failed to create SQLAlchemy engine or SQLDatabase: {e}", exc_info=True)
        db_engine = None
        db = None
else:
    logger.error("DATABASE_URL not found in settings. Cannot initialize SQL database connection.")

# --- Global SQL Agent (can be initialized once) ---
sql_agent_executor = None
if db and sql_generation_llm:
    try:
        # The SQLDatabaseToolkit provides the agent with tools to interact with the database
        # (e.g., list tables, get schema, run query, check query).
        toolkit = SQLDatabaseToolkit(db=db, llm=sql_generation_llm)
        
        # Create the SQL agent executor
        sql_agent_executor = create_sql_agent(
            llm=sql_generation_llm,
            toolkit=toolkit,
            verbose=True, # Very useful for debugging: shows agent's thoughts and SQL
            agent_type="openai-tools", # Or other compatible agent types, this often works well
                                       # even with non-OpenAI LLMs if they follow function calling well.
                                       # Might need adjustment based on Claude's capabilities with LangChain agent types.
            # You can add a prefix to the agent's prompt if needed:
            # prefix="You are an agent designed to interact with a SQL database. Given an input question, create a syntactically correct PostgreSQL query to run, then look at the results of the query and return the answer. Unless otherwise specified, do not query for more than 5 results. You can order results by a relevant column to return the most interesting examples in the database."
            handle_parsing_errors=True # Agent will try to recover from SQL syntax errors
        )
        logger.info("LangChain SQL Agent Executor created successfully.")
    except Exception as e:
        logger.error(f"Failed to create SQL Agent Executor: {e}", exc_info=True)
        sql_agent_executor = None
else:
    if not db:
        logger.error("SQL Database (db) not initialized. SQL Agent cannot be created.")
    if not sql_generation_llm:
        logger.error("SQL Generation LLM (sql_generation_llm) not initialized. SQL Agent cannot be created.")