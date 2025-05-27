import os
import logging
import re
from typing import Any, Dict, List, Optional

import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from sqlalchemy import create_engine, exc as sqlalchemy_exc
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain_core.prompts import PromptTemplate

from core.hackathon_llms import SyngentaHackathonLLM
from config.settings import settings

logger = logging.getLogger(__name__)

sql_llm_for_chain_instance: Optional[SyngentaHackathonLLM] = None
try:
    sql_llm_for_chain_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", temperature=0.0, max_tokens=2000
    )
    logger.info("LLM (Claude 3.5 Sonnet, temp=0.0) initialized for SQLDatabaseChain.")
except Exception as e:
    logger.error(f"Failed to initialize sql_llm_for_chain_instance: {e}", exc_info=True)

db_lc_wrapper: Optional[SQLDatabase] = None
if settings.DATABASE_URL and sql_llm_for_chain_instance:
    try:
        # Ensure DATABASE_URL from settings is used, not localhost if different
        # The DATABASE_URL in docker-compose for 'app' service is:
        # postgresql://syngenta_user:syngenta_password@postgres_db:5432/syngenta_supplychain_db
        # This should be correctly picked up by settings.DATABASE_URL
        db_engine = create_engine(str(settings.DATABASE_URL))
        
        # Log the actual DB URL being used by SQLAlchemy for clarity
        logger.info(f"SQLAlchemy engine connecting with URL: {str(settings.DATABASE_URL)}")

        with db_engine.connect() as connection_test:
            db_host_for_log = str(settings.DATABASE_URL).split('@')[-1].split('/')[0] if '@' in str(settings.DATABASE_URL) else str(settings.DATABASE_URL)
            logger.info(f"Successfully connected to database for SQLDatabase wrapper init. Using host: {db_host_for_log}")
        
        db_lc_wrapper = SQLDatabase(db_engine, include_tables=['supply_chain_transactions'])
        logger.info(f"LangChain SQLDatabase initialized. Using tables: {db_lc_wrapper.get_usable_table_names()}")
    except Exception as e:
        logger.error(f"Failed to create SQLDatabase wrapper or test connection (URL used: {settings.DATABASE_URL}): {e}", exc_info=True)
        db_lc_wrapper = None
else:
    if not settings.DATABASE_URL: logger.error("DATABASE_URL not found in settings.")
    if not sql_llm_for_chain_instance: logger.error("sql_llm_for_chain_instance not initialized.")
    logger.error("Cannot initialize LangChain SQLDatabase wrapper.")

_SQL_CHAIN_PROMPT_TEMPLATE_STR = """Given an input question, first create a syntactically correct {dialect} query to run, then look at the results of the query and return the answer.
Unless the user specifies in the question a specific number of examples to obtain, query for at most {top_k} results using the LIMIT clause as per {dialect}. You can order the results to return the most informative data as per {dialect}.
Never query for all columns from a table. You must query only the columns that are needed to answer the question. Wrap each column name in double quotes (") to denote them as delimited identifiers.
Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist. Also, pay attention to which column is in which table.
Pay attention to use CURRENT_DATE function to get the current date, if the question involves "today".

Your response for the SQL query part MUST be ONLY the SQL statement itself, immediately following the 'SQLQuery:' marker. Do NOT include any preamble, conversational text, or markdown formatting like ```sql around the SQL query.
If, after careful consideration of the table schema, you determine that a valid SQL query CANNOT be generated to answer the question, you MUST respond with ONLY the string 'NO_QUERY_POSSIBLE' immediately after the 'SQLQuery:' marker. Do not provide explanations in this case.

Use the following format for your entire multi-turn response structure:

Question: Question here
SQLQuery: SQL Query to run
SQLResult: Result of the SQLQuery
Answer: Final answer here

Only use the following tables:
{table_info}

Question: {input}"""

CUSTOM_SQL_PROMPT_OBJECT: Optional[PromptTemplate] = None
try:
    CUSTOM_SQL_PROMPT_OBJECT = PromptTemplate(
        input_variables=["input", "table_info", "dialect", "top_k"],
        template=_SQL_CHAIN_PROMPT_TEMPLATE_STR
    )
    logger.info("Custom SQL PromptTemplate created successfully.")
except Exception as e:
    logger.error(f"Failed to create CUSTOM_SQL_PROMPT_OBJECT: {e}", exc_info=True)

sql_database_chain_instance: Optional[SQLDatabaseChain] = None
if db_lc_wrapper and sql_llm_for_chain_instance and CUSTOM_SQL_PROMPT_OBJECT:
    try:
        sql_database_chain_instance = SQLDatabaseChain.from_llm(
            llm=sql_llm_for_chain_instance, db=db_lc_wrapper,
            prompt=CUSTOM_SQL_PROMPT_OBJECT, verbose=True, # verbose=True can be helpful
            return_intermediate_steps=True, top_k=10,
        )
        logger.info("LangChain SQLDatabaseChain created successfully with custom prompt.")
    except Exception as e:
        logger.error(f"Failed to create SQLDatabaseChain with custom prompt: {e}", exc_info=True)
        sql_database_chain_instance = None
elif db_lc_wrapper and sql_llm_for_chain_instance: # Fallback
    logger.warning("Custom prompt object not available. Attempting SQLDatabaseChain with default prompt.")
    try:
        sql_database_chain_instance = SQLDatabaseChain.from_llm(
            llm=sql_llm_for_chain_instance, db=db_lc_wrapper,
            verbose=True, return_intermediate_steps=True, top_k=10 # verbose=True
        )
        logger.info("LangChain SQLDatabaseChain created with default prompt.")
    except Exception as e_default:
        logger.error(f"Failed to create SQLDatabaseChain with default prompt: {e_default}", exc_info=True)
        sql_database_chain_instance = None
else:
    logger.error("Essential components for SQLDatabaseChain missing. Chain not created.")


def extract_sql_from_llm_output(llm_output_text: str) -> Optional[str]:
    if not llm_output_text or not isinstance(llm_output_text, str):
        logger.debug("extract_sql_from_llm_output: Received None or non-string input.")
        return None
    
    debug_input_repr = repr(llm_output_text) 
    logger.debug(f"extract_sql_from_llm_output: Full Input (repr): {debug_input_repr}")

    sql_query_marker = "SQLQuery:"
    last_marker_idx = llm_output_text.rfind(sql_query_marker)

    # This variable is initialized here but its value will be from 'text_after_initial_marker'
    # if the marker is found. It's used in a later log message.
    # text_after_initial_marker_for_log = "SQLQuery_marker_not_found_or_text_unavailable" 

    if last_marker_idx == -1:
        logger.warning(f"extract_sql_from_llm_output: '{sql_query_marker}' marker not found. Trying markdown block extraction.")
        match_md = re.search(r"```sql\s*([\s\S]*?)\s*```", llm_output_text, re.IGNORECASE | re.DOTALL)
        if match_md:
            sql_candidate_md = match_md.group(1).strip()
            if sql_candidate_md.upper() == "NO_QUERY_POSSIBLE":
                logger.info("extract_sql_from_llm_output: Found 'NO_QUERY_POSSIBLE' in markdown block.")
                return "NO_QUERY_POSSIBLE"
            sql_keywords_check = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
            if any(sql_candidate_md.upper().startswith(keyword) for keyword in sql_keywords_check):
                logger.debug(f"extract_sql_from_llm_output: Extracted SQL from markdown: '{sql_candidate_md}'")
                return sql_candidate_md
            logger.warning(f"extract_sql_from_llm_output: Markdown content ('{sql_candidate_md[:100]}...') not valid SQL/NQP.")
        return None

    text_after_initial_marker = llm_output_text[last_marker_idx + len(sql_query_marker):] 
    
    # CORRECTED LINE 1
    text_to_log_display_after_marker = text_after_initial_marker.replace(chr(10), "\\n") 
    logger.debug(f"extract_sql_from_llm_output: Raw text after last '{sql_query_marker}' marker: '{text_to_log_display_after_marker[:300]}...'")

    current_text_to_process = text_after_initial_marker.lstrip()
    if current_text_to_process.upper().startswith(sql_query_marker.upper()):
        current_text_to_process = current_text_to_process[len(sql_query_marker):].lstrip()
        # CORRECTED LINE 2
        text_to_log_display_current_process = current_text_to_process.replace(chr(10), "\\n")
        logger.debug(f"extract_sql_from_llm_output: Text after stripping repeated '{sql_query_marker}': '{text_to_log_display_current_process[:300]}...'")
    
    sql_candidate_isolated = current_text_to_process
    end_delimiters = ["\nSQLResult:", "\nAnswer:"] 
    min_end_pos = len(sql_candidate_isolated) 

    for delimiter in end_delimiters:
        pos = sql_candidate_isolated.find(delimiter)
        if pos != -1:
            min_end_pos = min(min_end_pos, pos)
    
    if min_end_pos == len(sql_candidate_isolated): 
        alt_end_delimiters = ["SQLResult:", "Answer:"]
        for delimiter in alt_end_delimiters:
            pos = sql_candidate_isolated.find(delimiter)
            if pos != -1:
                min_end_pos = min(min_end_pos, pos)

    sql_candidate_isolated = sql_candidate_isolated[:min_end_pos].strip()
    # CORRECTED LINE 3
    isolated_text_display = sql_candidate_isolated.replace(chr(10), "\\n")
    logger.debug(f"extract_sql_from_llm_output: Isolated text (potential SQL/NQP/explanation): '{isolated_text_display}'")

    temp_nqp_check = sql_candidate_isolated
    if temp_nqp_check.startswith("```sql"): temp_nqp_check = temp_nqp_check[len("```sql"):].strip()
    if temp_nqp_check.endswith("```"): temp_nqp_check = temp_nqp_check[:-len("```")].strip()
    
    if temp_nqp_check.upper() == "NO_QUERY_POSSIBLE":
        logger.info("extract_sql_from_llm_output: Identified 'NO_QUERY_POSSIBLE'.")
        return "NO_QUERY_POSSIBLE"

    final_sql_candidate = sql_candidate_isolated
    if final_sql_candidate.startswith("```sql"):
        final_sql_candidate = final_sql_candidate[len("```sql"):].strip()
        logger.debug(f"extract_sql_from_llm_output: final_sql_candidate after stripping ```sql prefix: '{final_sql_candidate}'")
    if final_sql_candidate.endswith("```"):
        final_sql_candidate = final_sql_candidate[:-len("```")].strip()
        logger.debug(f"extract_sql_from_llm_output: final_sql_candidate after stripping ``` suffix: '{final_sql_candidate}'")
    
    logger.debug(f"extract_sql_from_llm_output: Final candidate for keyword check: (repr) {repr(final_sql_candidate)}")

    sql_keywords = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")
    if final_sql_candidate and any(final_sql_candidate.upper().startswith(keyword) for keyword in sql_keywords):
        logger.debug(f"extract_sql_from_llm_output: Extracted valid SQL: '{final_sql_candidate}'")
        return final_sql_candidate
    
    if final_sql_candidate: 
        logger.warning(f"extract_sql_from_llm_output: Text ('{final_sql_candidate[:100]}...') does not start with known SQL keyword and is not 'NO_QUERY_POSSIBLE'. Returning as is (might be explanation).")
        return final_sql_candidate 
    else: 
        # CORRECTED LINE 4
        # 'text_after_initial_marker' contains the original text after the marker, if the marker was found.
        original_snippet_display = text_after_initial_marker.replace(chr(10), "\\n")
        logger.warning(f"extract_sql_from_llm_output: No useful SQL/NQP/explanation text extracted. `final_sql_candidate` is empty. Original text after initial SQLQuery marker was '{original_snippet_display[:100]}...'.")
        return None


def execute_natural_language_sql_query(user_query: str) -> Dict[str, Any]:
    if not sql_database_chain_instance:
        error_msg = "SQLDatabaseChain is not initialized. Cannot process SQL query."
        logger.error(error_msg)
        return {"answer": error_msg, "generated_sql": None, "error": error_msg}

    logger.info(f"Processing NL to SQL query: '{user_query}'")
    
    generated_sql_for_return = "Extraction_Not_Attempted_Or_Failed_Early"
    nl_answer = "No natural language answer processed by the chain (initial value)." 
    chain_response = None
    llm_raw_output_for_sql = "" 

    try:
        chain_response = sql_database_chain_instance.invoke(user_query)
        nl_answer = chain_response.get("result", "No natural language answer processed by the chain (after invoke).")
        
        intermediate_steps = chain_response.get("intermediate_steps", [])
        logger.debug(f"execute_natural_language_sql_query: Full intermediate_steps: (repr) {repr(intermediate_steps)}")
            
        # --- REFINED LOGIC TO FIND llm_raw_output_for_sql ---
        if intermediate_steps and isinstance(intermediate_steps, list):
            for step_content in intermediate_steps:
                if isinstance(step_content, str) and \
                   "SQLQuery:" in step_content and \
                   "SQLResult:" in step_content and \
                   "Answer:" in step_content:
                    llm_raw_output_for_sql = step_content
                    logger.debug(f"execute_natural_language_sql_query: Pass 1: Found ideal candidate (string step with all markers): {repr(llm_raw_output_for_sql)}")
                    break
            
            if not llm_raw_output_for_sql:
                for step_content in intermediate_steps:
                    if isinstance(step_content, dict):
                        for key in ["sql_cmd", "llm_output", "statement", "query", "log"]:
                            if key in step_content and isinstance(step_content[key], str) and \
                               "SQLQuery:" in step_content[key] and \
                               "SQLResult:" in step_content[key] and \
                               "Answer:" in step_content[key]:
                                llm_raw_output_for_sql = step_content[key]
                                logger.debug(f"execute_natural_language_sql_query: Pass 2: Found ideal candidate (dict step, key '{key}' with all markers): {repr(llm_raw_output_for_sql)}")
                                break
                    if llm_raw_output_for_sql: break 

            if not llm_raw_output_for_sql:
                for step_content in intermediate_steps:
                    if isinstance(step_content, str) and step_content.strip().upper().startswith("SQLQUERY:"):
                        if len(step_content.strip()) > len("SQLQuery:") + 5 and ("SELECT" in step_content.upper() or "WITH" in step_content.upper() or "NO_QUERY_POSSIBLE" in step_content.upper()):
                            llm_raw_output_for_sql = step_content
                            logger.debug(f"execute_natural_language_sql_query: Pass 3: Found candidate (string step starting with SQLQuery): {repr(llm_raw_output_for_sql)}")
                            break
                
                if not llm_raw_output_for_sql:
                    for step_content in intermediate_steps:
                        if isinstance(step_content, dict):
                            for key in ["sql_cmd", "query", "statement"]: 
                                if key in step_content and isinstance(step_content[key], str) and \
                                   step_content[key].strip().upper().startswith("SQLQUERY:"):
                                    if len(step_content[key].strip()) > len("SQLQuery:") + 5 and ("SELECT" in step_content[key].upper() or "WITH" in step_content[key].upper() or "NO_QUERY_POSSIBLE" in step_content[key].upper()):
                                        llm_raw_output_for_sql = step_content[key]
                                        logger.debug(f"execute_natural_language_sql_query: Pass 3: Found candidate (dict step, key '{key}' starting with SQLQuery): {repr(llm_raw_output_for_sql)}")
                                        break
                        if llm_raw_output_for_sql: break
            
            if not llm_raw_output_for_sql:
                if intermediate_steps and isinstance(intermediate_steps[0], dict) and \
                   "input" in intermediate_steps[0] and \
                   isinstance(intermediate_steps[0]["input"], str) and \
                   "SQLQuery:" in intermediate_steps[0]["input"]:
                    temp_input_val = intermediate_steps[0]["input"]
                    if "SQLResult:" in temp_input_val or "Answer:" in temp_input_val or len(temp_input_val) > len("SQLQuery:") + 30:
                        llm_raw_output_for_sql = temp_input_val
                        logger.debug(f"execute_natural_language_sql_query: Pass 4 (Last Resort Dict Input): Using input from first step: {repr(llm_raw_output_for_sql)}")
                    else:
                        logger.debug(f"execute_natural_language_sql_query: Pass 4: Skipped short 'input' from first step: {repr(temp_input_val)}")

        if not llm_raw_output_for_sql and isinstance(chain_response.get("query"), str) and "SQLQuery:" in chain_response.get("query"):
             llm_raw_output_for_sql = chain_response.get("query")
             logger.debug(f"execute_natural_language_sql_query: Using text from chain_response['query'] as final fallback: {repr(llm_raw_output_for_sql)}")
        # --- END OF REFINED LOGIC ---

        if llm_raw_output_for_sql:
            logger.info(f"execute_natural_language_sql_query: Final llm_raw_output_for_sql chosen for extraction: (repr) {repr(llm_raw_output_for_sql)}")
            generated_sql_for_return = extract_sql_from_llm_output(llm_raw_output_for_sql)
        else:
            logger.warning("execute_natural_language_sql_query: No text containing 'SQLQuery:' marker found suitable for extraction.")
            generated_sql_for_return = "SQL_EXTRACTION_FAILED_NO_RAW_SQLQUERY_TEXT_FOUND"

        sql_keywords_check = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")
        if generated_sql_for_return and any(generated_sql_for_return.upper().startswith(keyword) for keyword in sql_keywords_check):
            logger.info(f"SQL Chain NL Answer (after successful SQL execution by chain): {nl_answer}")
            logger.info(f"SQL Chain Extracted SQL (which was executed by chain):\n{generated_sql_for_return}")
            return {"answer": nl_answer, "generated_sql": generated_sql_for_return, "error": None}
        
        if generated_sql_for_return == "NO_QUERY_POSSIBLE":
            logger.info(f"LLM determined no valid SQL query. Chain result was: '{nl_answer}'")
            user_friendly_msg = "I cannot answer this question with a SQL query because the necessary information does not appear to be available in the database tables, or the query is outside the scope of the database."
            if nl_answer and ("cannot query" in nl_answer.lower() or "not possible" in nl_answer.lower() or "unable to find" in nl_answer.lower() or "don't have information" in nl_answer.lower()):
                user_friendly_msg = nl_answer 
            return {"answer": user_friendly_msg, "generated_sql": "NO_QUERY_POSSIBLE", "error": "Query cannot be answered with SQL (LLM decision)."}
        
        log_gen_sql = generated_sql_for_return[:100] if generated_sql_for_return else "None" 
        logger.warning(f"Extracted text '{log_gen_sql}...' not valid SQL/NQP. Chain result was: '{nl_answer[:100]}...'")
        explanation_answer = nl_answer 
        if "No natural language answer processed" in explanation_answer or user_query in explanation_answer or not explanation_answer.strip():
             explanation_answer = f"Could not generate a valid SQL query. The attempt resulted in: {generated_sql_for_return if generated_sql_for_return else 'No specific SQL generated or extraction failed.'}"
        return {"answer": explanation_answer, "generated_sql": generated_sql_for_return, "error": "Invalid SQL, explanation returned by LLM, or extraction failure."}

    except sqlalchemy_exc.ProgrammingError as e_sql:
        logger.error(f"SQL ProgrammingError for query '{user_query}': {e_sql.orig}", exc_info=False) # Set exc_info=False as orig often has a lot
        offending_sql = str(e_sql.statement).strip() if hasattr(e_sql, 'statement') and e_sql.statement else "Unavailable"
        
        if offending_sql.upper() == "NO_QUERY_POSSIBLE":
            logger.info("Caught ProgrammingError because chain attempted to execute 'NO_QUERY_POSSIBLE'.")
            user_friendly_msg = "I cannot answer this question with a SQL query as the required information does not appear to be available in the database tables, or the query is outside the scope of the database."
            if nl_answer and "No natural language answer processed" not in nl_answer and \
               ("cannot query" in nl_answer.lower() or "not possible" in nl_answer.lower() or "syntax error" in nl_answer.lower()): # check nl_answer too
                user_friendly_msg = nl_answer 
            return {"answer": user_friendly_msg, "generated_sql": "NO_QUERY_POSSIBLE", "error": "Query cannot be answered with SQL (LLM decision, caught at execution)."}
        else:
            logger.error(f"Offending SQL (from DB exception):\n{offending_sql}")
            return {"answer": f"There was an error executing the database query: {str(e_sql.orig)}", "generated_sql": offending_sql, "error": str(e_sql.orig)}
    
    except Exception as e:
        logger.error(f"Unexpected error during SQLDatabaseChain processing for query '{user_query}': {e}", exc_info=True)
        extracted_sql_check = "Unavailable_During_Exception"
        current_llm_raw_output = llm_raw_output_for_sql if llm_raw_output_for_sql else ""
        if not current_llm_raw_output and chain_response and isinstance(chain_response.get("query"), str) and "SQLQuery:" in chain_response.get("query"):
             current_llm_raw_output = chain_response.get("query")
        if current_llm_raw_output:
             extracted_sql_check = extract_sql_from_llm_output(current_llm_raw_output) # Call the fixed function

        if extracted_sql_check == "NO_QUERY_POSSIBLE":
             final_no_query_msg = "I cannot answer this question with a SQL query because the necessary information does not appear to be available in the database tables, or the query is outside the scope of the database."
             return {"answer": final_no_query_msg, "generated_sql": "NO_QUERY_POSSIBLE", "error": f"Query identified as NO_QUERY_POSSIBLE, but chain processing resulted in error: {str(e)}"}

        final_error_msg = nl_answer if nl_answer and "No natural language answer processed" not in nl_answer else f"An unexpected error occurred: {str(e)}"
        final_gen_sql = generated_sql_for_return if 'generated_sql_for_return' in locals() and generated_sql_for_return else extracted_sql_check
        return {"answer": final_error_msg, "generated_sql": final_gen_sql, "error": str(e)}

# --- Test block ---
if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # Set specific loggers to DEBUG for more detail during testing
        logging.getLogger('agents.sql_query_agent').setLevel(logging.DEBUG) 
        # logging.getLogger('langchain.sql_database').setLevel(logging.DEBUG) # For LangChain SQL Database logs
        # logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO) # For SQLAlchemy engine logs

    if not sql_database_chain_instance:
        logger.critical("SQLDatabaseChain NOT INITIALIZED. Attempting re-initialization for test.")
        if db_lc_wrapper and sql_llm_for_chain_instance and CUSTOM_SQL_PROMPT_OBJECT:
            try:
                sql_database_chain_instance = SQLDatabaseChain.from_llm(
                    llm=sql_llm_for_chain_instance, db=db_lc_wrapper, verbose=True, # Set verbose for chain output
                    return_intermediate_steps=True, top_k=10, prompt=CUSTOM_SQL_PROMPT_OBJECT
                )
                logger.info(f"Re-initialized SQLDatabaseChain in __main__.")
            except Exception as e_chain_reinit:
                logger.error(f"Failed re-init SQLDatabaseChain in __main__: {e_chain_reinit}")
        else: logger.error("Cannot re-initialize SQLDatabaseChain: components missing.")

    if not sql_database_chain_instance:
         logger.critical("SQLDatabaseChain STILL NOT INITIALIZED. Cannot run tests.")
    else:
        logger.info("\n--- TESTING SQLDatabaseChain DIRECTLY ---")
        test_sql_queries = [
            "What is the total sales amount for all orders?",
            "How many orders have an order_status of 'SUSPECTED_FRAUD'?",
            "What is the capital of France?", 
            "List all columns in the non_existent_table.", 
            "According to our inventory write-off policy, what was the total value of written-off inventory last year for product ID 'XYZ123'?",
        ]
        for i, query in enumerate(test_sql_queries):
            logger.info(f"\n--- Test SQL Query {i+1}/{len(test_sql_queries)}: '{query}' ---")
            result = execute_natural_language_sql_query(query)
            print(f"\n--- SQL Chain Result {i+1} ---")
            print(f"User Query: {query}")
            print(f"Generated SQL (extracted): {result.get('generated_sql', 'N/A')}")
            print(f"Answer: {result.get('answer')}")
            if result.get('error'):
                print(f"Error Message: {result.get('error')}")
            print("-----------------------------\n")
            
    logger.info("--- SQL Query tests in sql_query_agent.py finished ---")