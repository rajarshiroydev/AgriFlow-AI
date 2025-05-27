# SYNGENTA_AI_AGENT/agents/hybrid_orchestrator_agent.py

import logging
import json
import re 
from typing import Dict, Any, Optional, List # Added List

# Ensure sys.path modification is at the very top if needed for standalone execution,
# though ideally, running as a module or PYTHONPATH handles this.
# For direct script execution, this helps find 'core' and other 'agents'.
import sys
import os
PROJECT_ROOT_FOR_HYBRID = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT_FOR_HYBRID not in sys.path:
    sys.path.append(PROJECT_ROOT_FOR_HYBRID)

from core.hackathon_llms import SyngentaHackathonLLM
from agents.document_analyzer_agent import run_document_rag_query_direct
from agents.sql_query_agent import execute_natural_language_sql_query
# from config.settings import settings # LLM should get settings via its own import

logger = logging.getLogger(__name__)

# --- LLM Instance for Orchestration ---
orchestration_llm_instance: Optional[SyngentaHackathonLLM] = None
try:
    orchestration_llm_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", 
        temperature=0.1, 
        max_tokens=1500 # Increased for synthesis and refinement
    )
    logger.info("Orchestration LLM initialized for Hybrid Orchestrator.")
except Exception as e:
    logger.error(f"Failed to initialize orchestration_llm_instance for Hybrid Orchestrator: {e}", exc_info=True)


# --- Query Decomposition Prompt Template ---
QUERY_DECOMPOSITION_PROMPT_TEMPLATE = """
You are an expert query routing assistant. Your task is to analyze a user's question and determine if it needs to be answered using:
1. Policy Documents (for company policies, guidelines, definitions, risk frameworks, etc.)
2. Structured Database (for transactional data like sales, orders, customer details, product information, shipping logistics, etc.)
3. Both Policy Documents AND the Structured Database.

Based on the user's question, provide a JSON response with the following structure:

{{
  "query_type": "DOCUMENT_ONLY" | "DATABASE_ONLY" | "HYBRID" | "UNKNOWN",
  "document_question": "The specific question to ask the policy documents. (String, or null if not applicable)",
  "database_question": "The specific question to ask the structured database. (String, or null if not applicable)",
  "original_query": "The original user query (for reference)"
}}

Here's how to decide:

- If the question is about company rules, procedures, definitions (e.g., "What is our policy on X?", "How is Y defined?", "What are the guidelines for Z?"), it's likely "DOCUMENT_ONLY".
- If the question is about specific numbers, counts, lists of transactions, customer data, product details, sales figures, or operational metrics (e.g., "How many orders for product X?", "List all customers in city Y", "What is the total sales for region Z?"), it's likely "DATABASE_ONLY".
- If the question requires combining a policy/definition with specific data (e.g., "Find all late shipments according to the delivery policy definition of 'late'", "What is the financial impact of inventory write-offs based on the inventory write-off policy?", "List products that fall under the 'high-risk' category as defined in our supplier policy and their total sales."), it's "HYBRID".
- If the query is unclear or cannot be answered by either, use "UNKNOWN".

If it's a HYBRID query:
- The "document_question" should focus on extracting the relevant policy or definition.
- The "database_question" should be phrased so it can be answered by querying the database, potentially incorporating information that might be *found* from the document_question later. For now, just formulate the database part of the original question.

Example User Question: "What is our company's definition of slow-moving inventory according to the Inventory Management policy, and how many products currently fit this definition?"

Example JSON Response for Hybrid:
{{
  "query_type": "HYBRID",
  "document_question": "What is the company's definition of slow-moving inventory according to the Inventory Management policy?",
  "database_question": "How many products currently fit the definition of slow-moving inventory?",
  "original_query": "What is our company's definition of slow-moving inventory according to the Inventory Management policy, and how many products currently fit this definition?"
}}

Example User Question: "What is the total sales for last month?"

Example JSON Response for Database Only:
{{
  "query_type": "DATABASE_ONLY",
  "document_question": null,
  "database_question": "What is the total sales for last month?",
  "original_query": "What is the total sales for last month?"
}}

Example User Question: "What is the travel expense policy?"

Example JSON Response for Document Only:
{{
  "query_type": "DOCUMENT_ONLY",
  "document_question": "What is the travel expense policy?",
  "database_question": null,
  "original_query": "What is the travel expense policy?"
}}

Now, analyze the following user query:
User Query: "{user_query_placeholder}"

JSON Response:
"""

def _decompose_query_intent(user_query: str) -> Optional[Dict[str, Any]]:
    if not orchestration_llm_instance:
        logger.error("Orchestration LLM is not initialized. Cannot decompose query.")
        return None
    prompt = QUERY_DECOMPOSITION_PROMPT_TEMPLATE.format(user_query_placeholder=user_query)
    logger.info(f"Decomposing query intent for: '{user_query}'")
    logger.debug(f"Decomposition prompt sent to LLM (first 500 chars):\n{prompt[:500]}")
    try:
        response_text = orchestration_llm_instance._call(prompt=prompt)
        logger.debug(f"LLM response for decomposition (full):\n{response_text}")
        parsed_json = None 
        try:
            json_block_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text, re.DOTALL)
            if json_block_match:
                json_str = json_block_match.group(1).strip()
                parsed_json = json.loads(json_str)
            else:
                start_brace = response_text.find('{')
                end_brace = response_text.rfind('}')
                if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                    potential_json_str = response_text[start_brace : end_brace + 1]
                    parsed_json = json.loads(potential_json_str)
                else: # Try direct parsing as a last resort for clean JSON output
                    parsed_json = json.loads(response_text)
        except json.JSONDecodeError as e_json:
            logger.error(f"Could not parse JSON from LLM decomposition response: {e_json}. Response: {response_text[:500]}")
            return None
        
        if parsed_json is None: # Should not happen if above logic is complete, but as a safeguard
            logger.error(f"JSON parsing resulted in None. LLM response: {response_text[:500]}")
            return None
            
        required_keys = {"query_type", "document_question", "database_question", "original_query"}
        missing_keys = required_keys - set(parsed_json.keys())
        if missing_keys:
            logger.error(f"Parsed JSON from LLM is missing required keys: {missing_keys}. Parsed JSON: {parsed_json}")
            return None
        
        logger.info(f"Successfully decomposed query. Type: {parsed_json.get('query_type')}")
        return parsed_json
    except Exception as e:
        logger.error(f"Error during query decomposition LLM call: {e}", exc_info=True)
        return None

# --- Helper function for HYBRID path ---
def _refine_db_question_with_context(
    original_db_question: Optional[str], 
    document_context: Optional[str],
    original_user_query: str 
) -> Optional[str]:
    if not original_db_question:
        logger.info("_refine_db_question_with_context: No original DB question provided.")
        return None
    
    meaningless_contexts = ["No raw document context retrieved.", 
                            "Failed to get raw document context from RAG.",
                            "No document retrieval was performed as no document question was identified."]
    if not document_context or document_context.strip() == "" or document_context in meaningless_contexts:
        logger.info(f"_refine_db_question_with_context: No meaningful document context. Using original DB question: '{original_db_question}'")
        return original_db_question

    if not orchestration_llm_instance:
        logger.warning("_refine_db_question_with_context: Orchestration LLM not available. Using original DB question.")
        return original_db_question

    logger.info(f"_refine_db_question_with_context: Attempting to refine DB question: '{original_db_question}'")
    
    max_context_len = 2000 
    truncated_doc_context = str(document_context)[:max_context_len] # Ensure document_context is str
    if len(str(document_context)) > max_context_len:
        logger.debug(f"_refine_db_question_with_context: Document context truncated to {max_context_len} chars.")

    refinement_prompt = f"""The user's overall query was: "{original_user_query}"
The part of the query initially identified for the database is: "{original_db_question}"

Relevant context retrieved from company policy documents:
--- DOCUMENT CONTEXT START ---
{truncated_doc_context}
--- DOCUMENT CONTEXT END ---

Your task is to refine the "original database question" by incorporating any specific definitions, criteria, numerical thresholds, or conditions found in the "DOCUMENT CONTEXT" that are relevant to answering the database question AND can be translated into a SQL query.

For example:
- If the original DB question is "How many products are considered high value?" and the document context defines "high value product" as "any product with a unit price greater than $500",
  the refined DB question might be "How many products have a unit price greater than $500?".
- If the original DB question is "List all overdue shipments" and the document context states "A shipment is considered overdue if it is more than 3 days past its scheduled delivery date",
  the refined DB question might be "List all shipments where the actual shipping days are more than 3 days greater than the scheduled shipping days".

IMPORTANT: 
- If the DOCUMENT CONTEXT provides no specific, actionable information (like precise numbers, categories, or clear conditions) to make the original database question more precise for a SQL query, 
- OR if the original database question is already sufficiently precise and does not need context from the documents to be answered by SQL,
THEN RETURN THE ORIGINAL DATABASE QUESTION EXACTLY AS IT WAS.
- Do not invent new database fields or conditions not supported by the document context.
- The refined question must still be answerable by querying a typical transactional database.

Only output the refined database question (or the original one if no refinement is applicable). Do not add any preamble or explanation.

Refined Database Question:""".strip()

    try:
        logger.debug(f"_refine_db_question_with_context: Refinement prompt (first 600 chars via repr): {repr(refinement_prompt[:600])}...")
        refined_question_text = orchestration_llm_instance._call(prompt=refinement_prompt).strip()
        
        if not refined_question_text:
            logger.warning("_refine_db_question_with_context: LLM returned empty string for refinement. Using original.")
            return original_db_question

        if refined_question_text.lower() == original_db_question.lower(): # Case-insensitive comparison
            logger.info(f"_refine_db_question_with_context: LLM indicated no refinement needed or returned original. Original: '{original_db_question}'")
        else:
            logger.info(f"_refine_db_question_with_context: Original DB Q: '{original_db_question}', Refined DB Q by LLM: '{refined_question_text}'")
        
        return refined_question_text
    except Exception as e:
        logger.error(f"_refine_db_question_with_context: Error during LLM call for refinement: {e}", exc_info=True)
        return original_db_question 


def run_hybrid_query(user_query: str) -> Dict[str, Any]:
    logger.info(f"Received hybrid query request: '{user_query}'")
    
    sources: List[str] = []
    generated_sql: Optional[str] = None
    final_answer: str = "Processing..." 
    debug_info: str = ""
    query_type: Optional[str] = None
    doc_question: Optional[str] = None
    db_question: Optional[str] = None

    decomposed_intent = _decompose_query_intent(user_query)

    if not decomposed_intent:
        return {
            "answer": "I had trouble understanding your request. Could you please rephrase it?",
            "query_type_debug": "DECOMPOSITION_FAILED",
            "decomposed_doc_question_debug": None,
            "decomposed_db_question_debug": None,
            "sources": sources,
            "generated_sql": generated_sql,
            "debug_info_orchestrator": "Query decomposition failed.",
            "error": "Query decomposition failed."
        }

    query_type = decomposed_intent.get("query_type")
    doc_question = decomposed_intent.get("document_question")
    db_question = decomposed_intent.get("database_question")
    # original_query_from_decomp = decomposed_intent.get("original_query") # For reference

    if query_type == "DOCUMENT_ONLY":
        if doc_question:
            logger.info(f"Handling DOCUMENT_ONLY query: '{doc_question}'")
            rag_result = run_document_rag_query_direct(doc_question)
            final_answer = rag_result.get("answer", "No answer found from documents.")
            sources = rag_result.get("sources", [])
            debug_info = f"DOCUMENT_ONLY. RAG Answer: {final_answer[:100]}..."
        else:
            final_answer = "A document question was expected for DOCUMENT_ONLY but not provided by decomposition."
            debug_info = "DOCUMENT_ONLY but no doc_question."

    elif query_type == "DATABASE_ONLY":
        if db_question:
            logger.info(f"Handling DATABASE_ONLY query: '{db_question}'")
            sql_result = execute_natural_language_sql_query(db_question)
            final_answer = sql_result.get("answer", "No answer found from database.")
            generated_sql = sql_result.get("generated_sql")
            if sql_result.get("error"):
                final_answer += f" (DB Error: {sql_result.get('error')})"
            debug_info = f"DATABASE_ONLY. SQL Answer: {final_answer[:100]}..."
        else:
            final_answer = "A database question was expected for DATABASE_ONLY but not provided by decomposition."
            debug_info = "DATABASE_ONLY but no db_question."

    elif query_type == "HYBRID":
        logger.info(f"Handling HYBRID query. Original User Query: '{user_query}'. Decomposed Doc Q: '{doc_question}', Decomposed DB Q: '{db_question}'")
        
        rag_answer_text = "No document information retrieved or an error occurred."
        raw_doc_context_for_synthesis = "No raw document context retrieved." 

        if doc_question:
            logger.info(f"HYBRID: Step 1 - Retrieving document context for: '{doc_question}'")
            rag_result = run_document_rag_query_direct(doc_question)
            rag_answer_text = rag_result.get("answer", "Could not retrieve relevant document context from RAG.")
            raw_doc_context_for_synthesis = rag_result.get("raw_context", "Failed to get raw document context from RAG.")
            sources.extend(rag_result.get("sources", []))
            logger.info(f"HYBRID: RAG Answer snippet: {rag_answer_text[:100]}...")
            logger.debug(f"HYBRID: Raw Document Context snippet for synthesis: {str(raw_doc_context_for_synthesis)[:200]}...")
        else: 
            rag_answer_text = "No document-specific question was identified by decomposition for this hybrid query."
            raw_doc_context_for_synthesis = "No document retrieval was performed as no document question was identified."

        current_db_question_for_sql = db_question 
        if db_question: 
            refined_db_q = _refine_db_question_with_context(
                original_db_question=db_question,
                document_context=raw_doc_context_for_synthesis,
                original_user_query=user_query 
            )
            if refined_db_q: 
                current_db_question_for_sql = refined_db_q
        else: 
            current_db_question_for_sql = None
            logger.info("HYBRID: No initial database question from decomposition, skipping refinement and SQL query.")
        
        sql_response_text = "No database information retrieved (no query posed or an error occurred)."
        if current_db_question_for_sql: 
            logger.info(f"HYBRID: Step 2 - Querying database with (potentially refined): '{current_db_question_for_sql}'")
            sql_result = execute_natural_language_sql_query(current_db_question_for_sql)
            sql_response_text = sql_result.get("answer", "Failed to get answer from database query.")
            generated_sql = sql_result.get("generated_sql") 
            if sql_result.get("error"):
                sql_response_text += f" (DB Query Error: {sql_result.get('error')})"
                logger.warning(f"HYBRID: SQL query resulted in error: {sql_result.get('error')}")
        else:
             sql_response_text = "No database query was performed as no database question was formulated."
             generated_sql = "Not applicable (no DB question)."

        raw_context_display_for_synthesis = "N/A"
        meaningless_contexts = ["No raw document context retrieved.", 
                                "Failed to get raw document context from RAG.",
                                "No document retrieval was performed as no document question was identified."]
        if raw_doc_context_for_synthesis and raw_doc_context_for_synthesis not in meaningless_contexts:
            raw_context_display_for_synthesis = f'"""{str(raw_doc_context_for_synthesis)[:1500]}..."""'

        synthesis_prompt = f"""You are an AI assistant tasked with synthesizing information from multiple sources to answer a user's complex query.

The user's original overall query was: "{user_query}"

To address this, the query was broken down:
1. A question was posed to policy documents: "{doc_question or 'Not applicable (no document question identified).'}"
   - The answer/information derived from the documents was: "{rag_answer_text}"
   - (The raw document context used for this (snippet) was: {raw_context_display_for_synthesis})

2. A question was posed to the database: "{current_db_question_for_sql or 'Not applicable (no database question posed).'}" 
   (This might have been refined from an initial database sub-question of: "{db_question or 'N/A'}")
   - The answer/information derived from the database query was: "{sql_response_text}"
   - (The SQL query generated for this (if applicable) was: {generated_sql or 'Not applicable or query failed.'})

Your task is to provide a single, comprehensive, and easy-to-understand answer to the user's ORIGINAL query: "{user_query}".
Integrate the information from the policy documents and the database naturally.
- If one source provided an error or couldn't answer its part (e.g., "NO_QUERY_POSSIBLE" from database, or documents didn't contain info), acknowledge that briefly and focus on the information that WAS successfully retrieved.
- Do not simply list the answers from each source; synthesize them into a coherent narrative.
- Be direct and address all parts of the user's original question if possible.
- If crucial information is missing from one source that prevents a complete answer, state what's missing.

Final Comprehensive Answer:
"""
        final_answer = "Synthesis step failed or was not reached." 
        if orchestration_llm_instance:
            logger.info("HYBRID: Step 3 - Synthesizing final answer...")
            logger.debug(f"Synthesis prompt for HYBRID (first 600 chars):\n{synthesis_prompt[:600]}...")
            final_answer = orchestration_llm_instance._call(prompt=synthesis_prompt)
        else:
            final_answer = ( 
                f"Document Info (Answer): {rag_answer_text}\n"
                f"Database Info (Answer): {sql_response_text}\n"
                "(Synthesis LLM not available for combining)"
            )
        debug_info = f"HYBRID. RAG Answer: {rag_answer_text[:70]}... Raw Context used: {str(raw_doc_context_for_synthesis)[:70]}... DB Question: {str(current_db_question_for_sql)[:70]}... SQL Result: {sql_response_text[:70]}..."
    
    elif query_type == "UNKNOWN":
        final_answer = "I'm not sure how to answer that. Could you please provide more details or rephrase your question?"
        debug_info = "Query type UNKNOWN."
    else: # Should not happen ideally
        final_answer = f"Unrecognized query type '{query_type}' from decomposition. Please check logic."
        debug_info = f"Unrecognized query type: {query_type}"

    return {
        "answer": final_answer,
        "query_type_debug": query_type,
        "decomposed_doc_question_debug": doc_question,
        "decomposed_db_question_debug": db_question,
        "sources": sources, 
        "generated_sql": generated_sql, 
        "debug_info_orchestrator": debug_info,
        "error": None # Assuming errors from sub-functions are incorporated into their 'answer' fields
    }

# --- Test block ---
if __name__ == '__main__':
    # Ensure PROJECT_ROOT_FOR_HYBRID is available if this script is run directly
    # and settings.py relies on it for .env path
    # (It's set at the top of this file now)

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # For detailed logs during testing:
    logging.getLogger('agents.hybrid_orchestrator_agent').setLevel(logging.DEBUG) # This file's logs
    #logging.getLogger('agents.sql_query_agent').setLevel(logging.DEBUG)
    # logging.getLogger('core.hackathon_llms').setLevel(logging.DEBUG) # For LLM req/resp

    if not orchestration_llm_instance: 
        try:
            orchestration_llm_instance = SyngentaHackathonLLM(
                model_id="claude-3.5-sonnet", temperature=0.1, max_tokens=1500
            )
            logger.info("Orchestration LLM re-initialized for test in __main__.")
        except Exception as e:
            logger.error(f"Failed to re-initialize orchestration_llm_instance for test: {e}", exc_info=True)

    if not orchestration_llm_instance:
        logger.critical("Orchestration LLM not available. Cannot run hybrid query tests.")
    else:
        test_queries = [
            "What is the total sales amount for all orders?",
            "What is our company's policy on data privacy?",
            "According to our inventory write-off policy, what was the total value of written-off inventory last year for product ID 'XYZ123'?",
            "How many unique customer first names start with 'A' and what is the supplier code of conduct?",
            "Tell me a joke about supply chains." 
        ]

        for i, query in enumerate(test_queries):
            logger.info(f"\n--- Test Hybrid Query {i+1}/{len(test_queries)}: '{query}' ---")
            result = run_hybrid_query(query)
            print(f"\n--- Hybrid Query Result {i+1} ---")
            print(f"User Query: {query}")
            print(f"Returned Query Type (Debug): {result.get('query_type_debug')}")
            print(f"Decomposed Doc Q (Debug): {result.get('decomposed_doc_question_debug')}")
            print(f"Decomposed DB Q (Debug): {result.get('decomposed_db_question_debug')}")
            print(f"Generated SQL: {result.get('generated_sql')}")
            print(f"Sources: {result.get('sources')}")
            print(f"Final Answer:\n{result.get('answer')}")
            print(f"Orchestrator Debug Info: {result.get('debug_info_orchestrator')}")
            if result.get('error'): # If you add an explicit error key in the return
                 print(f"Orchestrator Error: {result.get('error')}")
            print("-----------------------------------\n")