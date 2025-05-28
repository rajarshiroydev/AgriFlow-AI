# SYNGENTA_AI_AGENT/agents/sql_query_agent.py

import os
import logging
import re
from typing import Any, Dict, Optional

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
from core.access_profiles import get_user_profile, DEFAULT_USER_ID

logger = logging.getLogger(__name__)

sql_llm_for_chain_instance: Optional[SyngentaHackathonLLM] = None
try:
    sql_llm_for_chain_instance = SyngentaHackathonLLM(model_id="claude-3.5-sonnet", temperature=0.0, max_tokens=2000)
    logger.info("LLM for SQLDatabaseChain initialized.")
except Exception as e:
    logger.error(f"Failed to initialize sql_llm_for_chain_instance: {e}", exc_info=True)

db_lc_wrapper: Optional[SQLDatabase] = None
# ... (db_lc_wrapper initialization same as your file) ...
if settings.DATABASE_URL and sql_llm_for_chain_instance:
    try:
        db_engine = create_engine(str(settings.DATABASE_URL))
        with db_engine.connect() as connection_test: pass 
        db_lc_wrapper = SQLDatabase(db_engine, include_tables=['supply_chain_transactions'])
        logger.info(f"LangChain SQLDatabase initialized for tables: {db_lc_wrapper.get_usable_table_names()} using URL ending with ...{str(settings.DATABASE_URL)[-30:]}")
    except Exception as e:
        logger.error(f"Failed to create SQLDatabase wrapper (URL: {settings.DATABASE_URL}): {e}", exc_info=True)
else:
    logger.error("Cannot initialize LangChain SQLDatabase wrapper: DB_URL or LLM missing.")


# MODIFIED PROMPT: The {input} will now contain both the actual question and the user_region_context.
# The LLM will be instructed to parse these from the {input}.
_SQL_CHAIN_PROMPT_TEMPLATE_STR = """You will be given a question and some user context.
First, understand the user's actual question and their regional context.
Then, create a syntactically correct {dialect} query to run based on the actual question and adhering to regional restrictions from the user context.
Finally, look at the results of the query and return the answer.

Unless the user specifies in their actual question a specific number of examples to obtain, query for at most {top_k} results using the LIMIT clause as per {dialect}.
Never query for all columns from a table. You must query only the columns that are needed. Wrap each column name in double quotes (") to denote them as delimited identifiers.
Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist. Also, pay attention to which column is in which table.
Pay attention to use CURRENT_DATE function to get the current date, if the question involves "today".

REGIONAL FILTERING RULES BASED ON USER CONTEXT:
- The user context will state the user's region or if they can view all regions.
- If the user's regional context is specific (e.g., 'User is restricted to data for the US region ONLY.') you MUST ensure that the generated SQL query filters data for ONLY that user's region.
- Assume a column named "Order_Region" exists in the 'supply_chain_transactions' table for this regional filtering. Example: Add 'AND "Order_Region" = \'US\'' or 'WHERE "Order_Region" = \'US\''.
- If the actual question explicitly asks for a different region AND the user context indicates 'User can view data for all regions', then you can query for that different region.
- If the user context is 'User can view data for all regions' or 'No specific regional restrictions apply', do not add an automatic regional filter unless the actual question itself specifies a region.

Your response for the SQL query part MUST be ONLY the SQL statement itself, immediately following the 'SQLQuery:' marker.
If, after careful consideration of the table schema and user context (especially regional restrictions), you determine that a valid SQL query CANNOT be generated to answer the actual question (e.g. user asking for EMEA data but context restricts them to US), you MUST respond with ONLY the string 'NO_QUERY_POSSIBLE' immediately after the 'SQLQuery:' marker.

Use the following format for your entire multi-turn response structure:
User Context (extracted from input): [The user context you understood]
Actual Question (extracted from input): [The actual question you understood]
SQLQuery: SQL Query to run
SQLResult: Result of the SQLQuery
Answer: Final answer here

Only use the following tables:
{table_info}

The input below contains the User Context and the Actual Question, formatted as:
"USER_CONTEXT_START <<user context string>> USER_CONTEXT_END ACTUAL_QUESTION_START <<actual question string>> ACTUAL_QUESTION_END"
Parse these carefully.

Input:
{input}
"""

# extract_sql_from_llm_output function remains exactly the same as your file

def extract_sql_from_llm_output(llm_output_text: str) -> Optional[str]:
    if not llm_output_text or not isinstance(llm_output_text, str): return None
    sql_query_marker = "SQLQuery:"
    last_marker_idx = llm_output_text.rfind(sql_query_marker)
    if last_marker_idx == -1:
        match_md = re.search(r"```sql\s*([\s\S]*?)\s*```", llm_output_text, re.IGNORECASE | re.DOTALL)
        if match_md:
            sql_candidate_md = match_md.group(1).strip()
            if sql_candidate_md.upper() == "NO_QUERY_POSSIBLE": return "NO_QUERY_POSSIBLE"
            if any(sql_candidate_md.upper().startswith(k) for k in ("SELECT", "WITH")): return sql_candidate_md
        return None
    text_after_marker = llm_output_text[last_marker_idx + len(sql_query_marker):]
    current_text = text_after_marker.lstrip()
    if current_text.upper().startswith(sql_query_marker.upper()): current_text = current_text[len(sql_query_marker):].lstrip()
    end_delimiters = ["\nSQLResult:", "\nAnswer:", "SQLResult:", "Answer:"] 
    min_end_pos = len(current_text)
    for delim in end_delimiters: 
        pos = current_text.find(delim)
        if pos != -1: min_end_pos = min(min_end_pos, pos)
    sql_candidate = current_text[:min_end_pos].strip()
    temp_nqp = sql_candidate.replace("```sql", "").replace("```", "").strip()
    if temp_nqp.upper() == "NO_QUERY_POSSIBLE": return "NO_QUERY_POSSIBLE"
    final_sql = sql_candidate.replace("```sql", "").replace("```", "").strip()
    sql_keywords = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")
    if final_sql and any(final_sql.upper().startswith(keyword) for keyword in sql_keywords): return final_sql
    return final_sql if final_sql else None


def execute_natural_language_sql_query(user_query: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    effective_user_id = user_id if user_id and user_id.strip() else DEFAULT_USER_ID
    
    if not db_lc_wrapper or not sql_llm_for_chain_instance:
        # ... (error handling same as your file) ...
        msg = "SQLDatabaseChain components (DB wrapper or LLM) not initialized."
        logger.error(msg)
        return {"answer": msg, "generated_sql": None, "error": msg}


    profile = get_user_profile(effective_user_id)
    user_region = profile.get("region", "GLOBAL")
    
    # This is the user_region_context string that will be part of the {input} to the chain
    region_context_string = f"Region: {user_region}."
    if "view_all_regions" in profile.get("permissions", []):
        region_context_string = "User can view data for all regions."
    elif user_region and user_region != "GLOBAL":
        region_context_string = f"User is restricted to data for the '{user_region}' region ONLY."
    else: 
        region_context_string = "No specific regional restrictions apply unless specified in the query."

    # Combine the actual user query and the regional context into a single input string
    # The prompt instructs the LLM on how to parse this.
    combined_input_for_chain = f"USER_CONTEXT_START <<{region_context_string}>> USER_CONTEXT_END ACTUAL_QUESTION_START <<{user_query}>> ACTUAL_QUESTION_END"

    logger.info(f"Processing NL to SQL for User: '{effective_user_id}'. Combined Input for Chain (snippet): {combined_input_for_chain[:200]}...")
    
    current_sql_chain = None
    try:
        # The prompt template now only strictly needs "input", "table_info", "dialect", "top_k"
        # because "user_region_context" is embedded within the "input" string.
        current_prompt = PromptTemplate(
            input_variables=["input", "table_info", "dialect", "top_k"], # Removed user_region_context from here
            template=_SQL_CHAIN_PROMPT_TEMPLATE_STR
        )
        current_sql_chain = SQLDatabaseChain.from_llm(
             llm=sql_llm_for_chain_instance, 
             db=db_lc_wrapper,
             prompt=current_prompt, 
             verbose=True, 
             return_intermediate_steps=True, 
             top_k=10,
             input_key="input" # This is where `combined_input_for_chain` will go
        )
    except Exception as e_prompt:
        logger.error(f"Failed to create SQLDatabaseChain for SQL agent: {e_prompt}", exc_info=True)
        return {"answer": "Error setting up SQL query processing.", "generated_sql": None, "error": str(e_prompt)}

    # ... (generated_sql_for_return, nl_answer, etc. initialization same as your file) ...
    generated_sql_for_return = "Not generated"
    nl_answer = "Processing..."
    chain_response = None
    llm_raw_output_for_sql = ""

    try:
        # The payload now only needs the "input" key for the SQLDatabaseChain
        chain_input_payload = { "input": combined_input_for_chain }
        
        logger.debug(f"Invoking SQLDatabaseChain with simplified payload: {chain_input_payload}")
        chain_response = current_sql_chain.invoke(chain_input_payload)
        
        # ... (rest of the processing for nl_answer, intermediate_steps, SQL extraction, and error handling) ...
        # ... is IDENTICAL to your provided file from this point onwards ...
        nl_answer = chain_response.get("result", "No natural language answer from chain.")
        intermediate_steps = chain_response.get("intermediate_steps", [])
        
        if intermediate_steps and isinstance(intermediate_steps, list):
            for step in intermediate_steps:
                if isinstance(step, dict) and "input" in step and "SQLQuery:" in step["input"] and "SQLResult:" in step["input"]:
                    llm_raw_output_for_sql = step["input"] 
                    break
            if not llm_raw_output_for_sql:
                for step in intermediate_steps: # Fallback
                    if isinstance(step, str) and "SQLQuery:" in step:
                        llm_raw_output_for_sql = step; break
                    elif isinstance(step, dict) and "statement" in step and "SQLQuery:" in step["statement"]:
                        llm_raw_output_for_sql = step["statement"]; break
        if not llm_raw_output_for_sql and isinstance(chain_response.get("query"), str) and "SQLQuery:" in chain_response.get("query"):
            llm_raw_output_for_sql = chain_response.get("query")

        if llm_raw_output_for_sql:
            generated_sql_for_return = extract_sql_from_llm_output(llm_raw_output_for_sql)
            logger.info(f"Extracted SQL for user {effective_user_id}: {generated_sql_for_return}")
        else:
            generated_sql_for_return = "SQL_EXTRACTION_FAILED_NO_RAW_TEXT"
            logger.warning(f"No raw text for SQL extraction. Full chain response: {chain_response}")

        if generated_sql_for_return == "NO_QUERY_POSSIBLE":
            logger.info(f"User {effective_user_id}: LLM determined NO_QUERY_POSSIBLE for query '{user_query}'. NL Answer: '{nl_answer}'")
            final_nl_answer = nl_answer
            if not final_nl_answer or "don't know" in final_nl_answer.lower() or user_query in final_nl_answer:
                 final_nl_answer = "Based on your permissions and the query, I cannot retrieve this specific data from the database."
            return {"answer": final_nl_answer, "generated_sql": "NO_QUERY_POSSIBLE", "error": "Query not possible or restricted."}
        elif generated_sql_for_return and any(generated_sql_for_return.upper().startswith(k) for k in ("SELECT", "WITH")):
            logger.info(f"User {effective_user_id}: Successfully generated SQL. NL Answer: {nl_answer}")
            return {"answer": nl_answer, "generated_sql": generated_sql_for_return, "error": None}
        else:
            logger.warning(f"User {effective_user_id}: Invalid SQL or extraction failure. Attempt: '{generated_sql_for_return}'. NL Answer: '{nl_answer}'")
            return {"answer": nl_answer if nl_answer and "No natural language answer" not in nl_answer else f"Could not generate a valid SQL query. Attempt: {generated_sql_for_return}", 
                    "generated_sql": generated_sql_for_return, "error": "Invalid SQL or extraction failed."}
    except sqlalchemy_exc.ProgrammingError as e_sql:
        offending_sql = str(e_sql.statement).strip() if hasattr(e_sql, 'statement') and e_sql.statement else generated_sql_for_return
        logger.error(f"SQL ProgrammingError for user {effective_user_id}, query '{user_query}': {e_sql.orig}. Offending SQL: {offending_sql}", exc_info=False)
        return {"answer": f"There was an error executing the database query: {str(e_sql.orig)}", "generated_sql": offending_sql, "error": str(e_sql.orig)}
    except Exception as e:
        logger.error(f"Unexpected SQL Chain Error for user {effective_user_id}, query '{user_query}': {e}", exc_info=True)
        return {"answer": f"An unexpected error occurred during SQL processing: {str(e)}", "generated_sql": generated_sql_for_return, "error": str(e)}

# if __name__ == '__main__': block remains IDENTICAL to your file
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    test_scenarios_sql = [
        {"user_id": "guest_global", "query": "What is the total sales for all orders?"},
        {"user_id": "analyst_us", "query": "Total sales?"}, 
        {"user_id": "analyst_us", "query": "Total sales in EMEA?"},
        {"user_id": "manager_emea", "query": "What is the profit margin for products in EMEA?"},
        {"user_id": "admin_global", "query": "What are the total sales in US and EMEA combined?"}
    ]

    for i, scenario in enumerate(test_scenarios_sql):
        print(f"\n--- SQL Agent Test {i+1}: User '{scenario['user_id']}', Query: '{scenario['query']}' ---")
        result = execute_natural_language_sql_query(user_query=scenario["query"], user_id=scenario["user_id"])
        print(f"  Generated SQL: {result.get('generated_sql')}")
        print(f"  Answer: {result.get('answer')}")
        if result.get('error'):
            print(f"  Error: {result.get('error')}")
        print("-" * 40)