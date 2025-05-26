# SYNGENTA_AI_AGENT/agents/sql_query_agent.py
import os
import logging
import re 
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, exc as sqlalchemy_exc
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain 
from langchain_core.prompts import PromptTemplate # Correct import for PromptTemplate

from core.hackathon_llms import SyngentaHackathonLLM 
from config.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize LLM for SQLDatabaseChain ---
sql_llm_for_chain_instance: Optional[SyngentaHackathonLLM] = None
try:
    sql_llm_for_chain_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", 
        temperature=0.0, 
        max_tokens=2000 
    )
    logger.info("LLM (Claude 3.5 Sonnet, temp=0.0) initialized for SQLDatabaseChain.")
except Exception as e:
    logger.error(f"Failed to initialize sql_llm_for_chain_instance: {e}", exc_info=True)

# --- Initialize Database Connection for LangChain ---
db_lc_wrapper: Optional[SQLDatabase] = None
if settings.DATABASE_URL and sql_llm_for_chain_instance: # Ensure LLM is also ready
    try:
        db_engine = create_engine(str(settings.DATABASE_URL))
        db_lc_wrapper = SQLDatabase(
            db_engine, 
            include_tables=['supply_chain_transactions']
        )
        logger.info(f"LangChain SQLDatabase initialized. Using tables: {db_lc_wrapper.get_usable_table_names()}")
    except Exception as e:
        logger.error(f"Failed to create SQLDatabase wrapper: {e}", exc_info=True)
        db_lc_wrapper = None # Ensure it's None if init fails
else:
    if not settings.DATABASE_URL: logger.error("DATABASE_URL not found in settings.")
    if not sql_llm_for_chain_instance: logger.error("sql_llm_for_chain_instance not initialized for DB wrapper.")
    logger.error("Cannot initialize LangChain SQLDatabase wrapper.")

# --- Custom Prompt for SQLDatabaseChain ---
# This template string includes all placeholders SQLDatabaseChain will fill.
_SQL_CHAIN_PROMPT_TEMPLATE_STR = """Given an input question, first create a syntactically correct {dialect} query to run, then look at the results of the query and return the answer.
Unless the user specifies in the question a specific number of examples to obtain, query for at most {top_k} results using the LIMIT clause as per {dialect}. You can order the results to return the most informative data as per {dialect}.
Never query for all columns from a table. You must query only the columns that are needed to answer the question. Wrap each column name in double quotes (") to denote them as delimited identifiers.
Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist. Also, pay attention to which column is in which table.
Pay attention to use CURRENT_DATE function to get the current date, if the question involves "today".

Your response for the SQL query part MUST be ONLY the SQL statement itself, immediately following the 'SQLQuery:' marker. Do NOT include any preamble, conversational text, or markdown formatting like ```sql around the SQL query.

Use the following format for your entire multi-turn response structure:

Question: Question here
SQLQuery: SQL Query to run
SQLResult: Result of the SQLQuery
Answer: Final answer here

Only use the following tables:
{table_info}

Question: {input}""" # SQLDatabaseChain appends "SQLQuery:" and expects LLM to continue

CUSTOM_SQL_PROMPT_OBJECT: Optional[PromptTemplate] = None
# We define CUSTOM_SQL_PROMPT_OBJECT here. It needs input_variables that the chain will provide.
# 'dialect' is provided by the SQLDatabase object (db_lc_wrapper).
# 'top_k', 'table_info', 'input' are provided by the chain during its execution.
try:
    CUSTOM_SQL_PROMPT_OBJECT = PromptTemplate(
        input_variables=["input", "table_info", "dialect", "top_k"], 
        template=_SQL_CHAIN_PROMPT_TEMPLATE_STR
    )
    logger.info("Custom SQL PromptTemplate created successfully.")
except Exception as e:
    logger.error(f"Failed to create CUSTOM_SQL_PROMPT_OBJECT: {e}", exc_info=True)


# --- LangChain SQL Database Chain ---
sql_database_chain_instance: Optional[SQLDatabaseChain] = None
if db_lc_wrapper and sql_llm_for_chain_instance:
    if CUSTOM_SQL_PROMPT_OBJECT:
        try:
            sql_database_chain_instance = SQLDatabaseChain.from_llm(
                llm=sql_llm_for_chain_instance,
                db=db_lc_wrapper,
                prompt=CUSTOM_SQL_PROMPT_OBJECT, # Using the custom prompt object
                verbose=True, 
                return_intermediate_steps=True, 
                top_k=10 
            )
            logger.info("LangChain SQLDatabaseChain created successfully with custom prompt.")
        except Exception as e:
            logger.error(f"Failed to create SQLDatabaseChain with custom prompt: {e}", exc_info=True)
            sql_database_chain_instance = None 
    
    if not sql_database_chain_instance: 
        logger.warning("Attempting SQLDatabaseChain with default prompt due to custom prompt failure or it not being initialized.")
        try:
            sql_database_chain_instance = SQLDatabaseChain.from_llm(
                llm=sql_llm_for_chain_instance,
                db=db_lc_wrapper,
                verbose=True, 
                return_intermediate_steps=True, 
                top_k=10
            )
            logger.info("LangChain SQLDatabaseChain created successfully with default prompt.")
        except Exception as e_default:
            logger.error(f"Failed to create SQLDatabaseChain with default prompt: {e_default}", exc_info=True)
            sql_database_chain_instance = None 
else:
    logger.error("SQLDatabase or LLM for chain not initialized. SQLDatabaseChain cannot be created.")


def extract_sql_from_llm_output(llm_output_text: str) -> Optional[str]:
    if not llm_output_text or not isinstance(llm_output_text, str): return None
    logger.debug(f"Attempting to extract SQL from LLM output snippet: {llm_output_text[:300]}...")
    sql_query_marker = "SQLQuery:"
    last_marker_idx = llm_output_text.rfind(sql_query_marker)
    extracted_sql = None
    if last_marker_idx != -1:
        potential_sql_block = llm_output_text[last_marker_idx + len(sql_query_marker):].strip()
        sql_candidate = potential_sql_block.split("SQLResult:")[0].split("Answer:")[0].strip()
        if sql_candidate.startswith("```sql"): sql_candidate = sql_candidate[len("```sql"):].strip()
        if sql_candidate.endswith("```"): sql_candidate = sql_candidate[:-len("```")].strip()
        if sql_candidate.upper().startswith("SELECT"):
            extracted_sql = sql_candidate
            logger.debug(f"Extracted SQL (via last SQLQuery: marker): {extracted_sql}")
    if not extracted_sql:
        match = re.search(r"```sql\s*([\s\S]*?)\s*```", llm_output_text, re.IGNORECASE)
        if match:
            sql_candidate = match.group(1).strip()
            if sql_candidate.upper().startswith("SELECT"):
                extracted_sql = sql_candidate
                logger.debug(f"Extracted SQL (via markdown block): {extracted_sql}")
    if not extracted_sql: logger.warning(f"Could not extract clear SQL query from: {llm_output_text[:300]}...")
    return extracted_sql

def execute_natural_language_sql_query(user_query: str) -> Dict[str, Any]:
    if not sql_database_chain_instance:
        error_msg = "SQLDatabaseChain is not initialized."
        logger.error(error_msg)
        return {"answer": error_msg, "generated_sql": None, "error": error_msg}
    logger.info(f"Processing NL to SQL query: '{user_query}'")
    try:
        chain_response = sql_database_chain_instance.invoke(user_query)
        nl_answer = chain_response.get("result", "No natural language answer processed by the chain.")
        generated_sql = "SQL query not found or not extracted."
        intermediate_steps = chain_response.get("intermediate_steps", [])
        if intermediate_steps and isinstance(intermediate_steps, list):
            for step_content in intermediate_steps:
                if isinstance(step_content, str):
                    extracted = extract_sql_from_llm_output(step_content)
                    if extracted: generated_sql = extracted; break
                elif isinstance(step_content, dict):
                    for key in ["sql_cmd", "query", "statement", "input", "llm_output"]: 
                        if key in step_content and isinstance(step_content[key], str):
                            extracted = extract_sql_from_llm_output(step_content[key])
                            if extracted: generated_sql = extracted; break
                    if "SELECT " in generated_sql.upper(): break
        logger.info(f"SQL Chain NL Answer: {nl_answer}")
        if "SELECT " in generated_sql.upper(): logger.info(f"SQL Chain Extracted SQL:\n{generated_sql}")
        else: logger.warning(f"Could not confidently extract SQL. Check verbose logs. Steps: {intermediate_steps}")
        return {"answer": nl_answer, "generated_sql": generated_sql, "error": None}
    except sqlalchemy_exc.ProgrammingError as e_sql:
        logger.error(f"SQL ProgrammingError for query '{user_query}': {e_sql.orig}", exc_info=False)
        offending_sql = str(e_sql.statement) if hasattr(e_sql, 'statement') and e_sql.statement else "Unavailable"
        if offending_sql == "Unavailable" and hasattr(e_sql, 'params') and e_sql.params:
            if isinstance(e_sql.params, (tuple, list)) and e_sql.params and isinstance(e_sql.params[0], str): offending_sql = e_sql.params[0]
            elif isinstance(e_sql.params, str): offending_sql = e_sql.params
        logger.error(f"Offending SQL (from exception):\n{offending_sql}")
        return {"answer": f"Error executing SQL: {str(e_sql.orig)}", "generated_sql": offending_sql, "error": str(e_sql.orig)}
    except Exception as e:
        logger.error(f"Error during SQLDatabaseChain execution for query '{user_query}': {e}", exc_info=True)
        return {"answer": f"Error processing SQL query: {str(e)}", "generated_sql": None, "error": str(e)}

# --- Test block ---
if __name__ == '__main__':
    PROJECT_BASE_DIR_MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(PROJECT_BASE_DIR_MAIN, '.env')
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        logger.info(f"Loading .env file from: {env_path} for sql_query_agent.py test.")
        load_dotenv(dotenv_path=env_path)
        
        # Re-initialization logic for components if they failed at module level
        if not sql_llm_for_chain_instance:
            try: sql_llm_for_chain_instance = SyngentaHackathonLLM(model_id="claude-3.5-sonnet",temperature=0.0,max_tokens=2000)
            except Exception as e: logger.error(f"Failed re-init sql_llm: {e}")
        if not db_lc_wrapper and settings.DATABASE_URL and sql_llm_for_chain_instance:
            try:
                db_engine = create_engine(str(settings.DATABASE_URL))
                db_lc_wrapper = SQLDatabase(db_engine, include_tables=['supply_chain_transactions'])
            except Exception as e: logger.error(f"Failed re-init SQLDatabase: {e}")
        
        # Define CUSTOM_PROMPT_OBJECT for re-initialization in __main__
        # This ensures it uses the same prompt as the module-level one
        _SQL_CHAIN_PROMPT_TEMPLATE_STR_MAIN = _SQL_CHAIN_PROMPT_TEMPLATE_STR # Use the same template string
        CUSTOM_SQL_PROMPT_OBJECT_MAIN: Optional[PromptTemplate] = None
        if db_lc_wrapper : # Only if db_lc_wrapper is valid
             try:
                 CUSTOM_SQL_PROMPT_OBJECT_MAIN = PromptTemplate(
                     input_variables=["input", "table_info", "dialect", "top_k"],
                     template=_SQL_CHAIN_PROMPT_TEMPLATE_STR_MAIN
                 )
                 logger.info("Custom SQL PromptTemplate (for __main__ re-init) created.")
             except Exception as e_prompt_main:
                 logger.error(f"Failed to create CUSTOM_SQL_PROMPT_OBJECT_MAIN: {e_prompt_main}")
        
        if not sql_database_chain_instance and db_lc_wrapper and sql_llm_for_chain_instance:
            prompt_to_use_for_reinit = CUSTOM_SQL_PROMPT_OBJECT_MAIN if CUSTOM_SQL_PROMPT_OBJECT_MAIN else None
            log_msg_prompt_type = "custom prompt" if prompt_to_use_for_reinit else "default prompt"
            try:
                sql_database_chain_instance = SQLDatabaseChain.from_llm(
                    llm=sql_llm_for_chain_instance, db=db_lc_wrapper, verbose=True, 
                    return_intermediate_steps=True, top_k=10,
                    prompt=prompt_to_use_for_reinit # Use custom prompt if available, else None (default)
                )
                logger.info(f"Re-initialized SQLDatabaseChain with {log_msg_prompt_type} in __main__.")
            except Exception as e_chain: 
                logger.error(f"Failed re-init SQLDatabaseChain with {log_msg_prompt_type} in __main__: {e_chain}")
    else:
        logger.warning(f".env file not found for test.")

    if not sql_database_chain_instance:
        logger.critical("SQLDatabaseChain NOT INITIALIZED. Cannot run tests.")
    else:
        logger.info("\n--- TESTING SQLDatabaseChain DIRECTLY (with custom prompt logic) ---")
        test_sql_queries = [
            "What is the total sales amount for all orders?",
            "How many orders have an order_status of 'SUSPECTED_FRAUD'?",
            "List the first 3 unique customer first names (customer_fname) from Caguas city.",
            "What are the top 2 order regions by total sales? Show region and total sales.",
            "Count the number of late deliveries based on late_delivery_risk being greater than 0.",
            "Which product (product_name) has the highest benefit per order? List the product name and its benefit per order.",
            "What is the average number of days for real shipping (days_for_shipping_real) for orders in the 'West' market?"
        ]
        for i, query in enumerate(test_sql_queries):
            logger.info(f"\n--- Test SQL Query {i+1}/{len(test_sql_queries)}: '{query}' ---")
            result = execute_natural_language_sql_query(query)
            print(f"\n--- SQL Chain Result {i+1} ---")
            print(f"User Query: {query}")
            print(f"Generated SQL (extracted):\n{result.get('generated_sql')}")
            print(f"Answer: {result.get('answer')}")
            if result.get('error'):
                print(f"Error: {result.get('error')}")
            print("-----------------------------\n")
            
    logger.info("--- SQL Query tests in sql_query_agent.py finished ---")