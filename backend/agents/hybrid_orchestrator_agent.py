import logging
import json
import re 
from typing import Dict, Any, Optional, List

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

logger = logging.getLogger(__name__)

orchestration_llm_instance: Optional[SyngentaHackathonLLM] = None
try:
    orchestration_llm_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", 
        temperature=0.1, 
        max_tokens=2500 # Slightly increased for history
    )
    logger.info("Orchestration LLM initialized for Hybrid Orchestrator.")
except Exception as e:
    logger.error(f"Failed to initialize orchestration_llm_instance for Hybrid Orchestrator: {e}", exc_info=True)

def _format_history_for_prompt(history: Optional[List[Any]], max_turns: int = 3) -> str:
    # The `history` parameter from run_hybrid_query will be List[HistoryMessage]
    if not history:
        return "No conversation history provided."
    
    # Ensure we're only taking the last N turns based on pairs
    effective_history = history[-(max_turns * 2):] 

    if not effective_history:
        return "No recent conversation history to display."

    formatted_history_lines = ["Previous conversation turns (most recent last):"]
    for msg_obj in effective_history: # msg_obj is a HistoryMessage Pydantic object
        sender = msg_obj.sender.capitalize() # Pydantic fields are attributes
        text = msg_obj.text
        formatted_history_lines.append(f"{sender}: {text}")
    return "\n".join(formatted_history_lines)

QUERY_DECOMPOSITION_PROMPT_TEMPLATE = """
You are an expert query routing assistant. Your task is to analyze a user's CURRENT question, considering the CONVERSATION HISTORY if provided, and determine if the CURRENT question needs to be answered using:
1. Policy Documents
2. Structured Database
3. Both Policy Documents AND the Structured Database.

CONVERSATION HISTORY:
{conversation_history_placeholder}

Based on the user's CURRENT question, provide a JSON response with the following structure:
{{
  "query_type": "DOCUMENT_ONLY" | "DATABASE_ONLY" | "HYBRID" | "UNKNOWN",
  "document_question": "The specific question to ask the policy documents based on the CURRENT user query and history. (String, or null if not applicable)",
  "database_question": "The specific question to ask the structured database based on the CURRENT user query and history. (String, or null if not applicable)",
  "original_query": "The original CURRENT user query (for reference)"
}}

Guidelines:
- Focus on resolving the CURRENT user query. The history provides context.
- "DOCUMENT_ONLY": For company rules, procedures, definitions.
- "DATABASE_ONLY": For specific numbers, counts, lists of transactions, operational metrics.
- "HYBRID": If the question combines policy/definition with specific data.
- "UNKNOWN": If the query is unclear or unanswerable.

If it's a HYBRID query, formulate sub-questions using history for context.

Example for HYBRID with history:
CONVERSATION HISTORY:
User: What is our company's definition of slow-moving inventory?
AI: The policy defines slow-moving inventory as items with no sales in the last 180 days.
CURRENT User Query: "And how many products currently fit this definition?"
Example JSON Response:
{{
  "query_type": "HYBRID",
  "document_question": "What is the company's definition of slow-moving inventory according to the Inventory Management policy?",
  "database_question": "How many products have had no sales in the last 180 days?",
  "original_query": "And how many products currently fit this definition?"
}}

Now, analyze the following:
CURRENT User Query: "{user_query_placeholder}"

JSON Response:
"""

def _decompose_query_intent(user_query: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
    if not orchestration_llm_instance:
        logger.error("Orchestration LLM is not initialized. Cannot decompose query.")
        return None
    
    formatted_history = _format_history_for_prompt(history)
    prompt = QUERY_DECOMPOSITION_PROMPT_TEMPLATE.format(
        conversation_history_placeholder=formatted_history,
        user_query_placeholder=user_query
    )
    logger.info(f"Decomposing query intent for: '{user_query}' (History turns: {len(history) if history else 0})")
    logger.debug(f"Decomposition prompt (first 500 chars):\n{prompt[:500]}")
    try:
        response_text = orchestration_llm_instance._call(prompt=prompt)
        logger.debug(f"LLM response for decomposition:\n{response_text}")
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
                else: 
                    parsed_json = json.loads(response_text)
        except json.JSONDecodeError as e_json:
            logger.error(f"Could not parse JSON from LLM decomposition response: {e_json}. Response: {response_text[:500]}")
            return None
        
        if parsed_json is None:
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

def _refine_db_question_with_context(
    original_db_question: Optional[str], 
    document_context: Optional[str],
    original_user_query: str 
) -> Optional[str]:
    if not original_db_question:
        return None
    
    meaningless_contexts = ["No raw document context retrieved.", 
                            "Failed to get raw document context from RAG.",
                            "No document retrieval was performed as no document question was identified."]
    if not document_context or document_context.strip() == "" or document_context in meaningless_contexts:
        return original_db_question

    if not orchestration_llm_instance:
        return original_db_question

    logger.info(f"_refine_db_question_with_context: Refining DB question: '{original_db_question}' based on user query: '{original_user_query}'")
    
    max_context_len = 2000 
    truncated_doc_context = str(document_context)[:max_context_len]

    refinement_prompt = f"""The user's current overall query (potentially clarified by conversation history) was: "{original_user_query}"
The part of the query identified for the database is: "{original_db_question}"

Relevant context retrieved from company policy documents:
--- DOCUMENT CONTEXT START ---
{truncated_doc_context}
--- DOCUMENT CONTEXT END ---

Your task is to refine the "original database question" by incorporating any specific definitions, criteria, numerical thresholds, or conditions found in the "DOCUMENT CONTEXT" that are relevant to answering the database question AND can be translated into a SQL query.
If the DOCUMENT CONTEXT provides no specific, actionable information OR if the original database question is already sufficiently precise, THEN RETURN THE ORIGINAL DATABASE QUESTION EXACTLY AS IT WAS.
Do not invent new database fields or conditions. The refined question must still be answerable by querying a typical transactional database.
Only output the refined database question (or the original one if no refinement is applicable).

Refined Database Question:""".strip()

    try:
        refined_question_text = orchestration_llm_instance._call(prompt=refinement_prompt).strip()
        if not refined_question_text: return original_db_question
        if refined_question_text.lower() != original_db_question.lower():
            logger.info(f"Refined DB Q by LLM: '{refined_question_text}' (Original: '{original_db_question}')")
        return refined_question_text
    except Exception as e:
        logger.error(f"_refine_db_question_with_context: Error: {e}", exc_info=True)
        return original_db_question 

def run_hybrid_query(user_query: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    logger.info(f"Received hybrid query request: '{user_query}' (History turns: {len(history) if history else 0})")
    
    sources: List[str] = []
    generated_sql: Optional[str] = None
    final_answer: str = "Processing..." 
    debug_info: str = ""
    query_type: Optional[str] = None
    doc_question_decomposed: Optional[str] = None
    db_question_decomposed: Optional[str] = None

    decomposed_intent = _decompose_query_intent(user_query, history)

    if not decomposed_intent:
        return {
            "answer": "I had trouble understanding your request. Could you please rephrase it?",
            "query_type_debug": "DECOMPOSITION_FAILED", "decomposed_doc_question_debug": None,
            "decomposed_db_question_debug": None, "sources": [], "generated_sql": None,
            "debug_info_orchestrator": "Query decomposition failed.", "error": "Query decomposition failed."
        }

    query_type = decomposed_intent.get("query_type")
    doc_question_decomposed = decomposed_intent.get("document_question")
    db_question_decomposed = decomposed_intent.get("database_question")
    original_query_from_decomp = decomposed_intent.get("original_query", user_query)

    rag_answer_text = "No document information was sought or retrieved."
    raw_doc_context_for_synthesis = "No document retrieval was performed."
    sql_response_text = "No database information was sought or retrieved."

    if query_type == "DOCUMENT_ONLY":
        if doc_question_decomposed:
            rag_result = run_document_rag_query_direct(doc_question_decomposed)
            final_answer = rag_result.get("answer", "No answer found from documents.")
            sources = rag_result.get("sources", [])
        else:
            final_answer = "Document question expected but not provided by decomposition."

    elif query_type == "DATABASE_ONLY":
        if db_question_decomposed:
            sql_result = execute_natural_language_sql_query(db_question_decomposed)
            final_answer = sql_result.get("answer", "No answer found from database.")
            generated_sql = sql_result.get("generated_sql")
            if sql_result.get("error"): final_answer += f" (DB Error: {sql_result.get('error')})"
        else:
            final_answer = "Database question expected but not provided by decomposition."

    elif query_type == "HYBRID":
        if doc_question_decomposed:
            rag_result = run_document_rag_query_direct(doc_question_decomposed)
            rag_answer_text = rag_result.get("answer", "Could not retrieve relevant document context.")
            raw_doc_context_for_synthesis = rag_result.get("raw_context", "Failed to get raw document context.")
            sources.extend(rag_result.get("sources", []))
        
        current_db_question_for_sql = db_question_decomposed
        if db_question_decomposed: 
            refined_db_q = _refine_db_question_with_context(
                original_db_question=db_question_decomposed,
                document_context=raw_doc_context_for_synthesis,
                original_user_query=original_query_from_decomp 
            )
            if refined_db_q: current_db_question_for_sql = refined_db_q
        
        if current_db_question_for_sql: 
            sql_result = execute_natural_language_sql_query(current_db_question_for_sql)
            sql_response_text = sql_result.get("answer", "Failed to get answer from database.")
            generated_sql = sql_result.get("generated_sql") 
            if sql_result.get("error"): sql_response_text += f" (DB Error: {sql_result.get('error')})"
        else:
             sql_response_text = "No database query was performed (no question after refinement)."
             generated_sql = "Not applicable."

        formatted_history_for_synthesis = _format_history_for_prompt(history, max_turns=2)
        synthesis_prompt = f"""You are an AI assistant synthesizing information to answer a user's CURRENT query, considering the CONVERSATION HISTORY.

CONVERSATION HISTORY:
{formatted_history_for_synthesis}

The user's CURRENT overall query was: "{user_query}" 

To address the CURRENT query, it was broken down:
1. Question to policy documents: "{doc_question_decomposed or 'Not applicable.'}"
   - Info from documents: "{rag_answer_text}"
2. Question to database: "{current_db_question_for_sql or 'Not applicable.'}"
   - Info from database: "{sql_response_text}"
   - (Generated SQL: {generated_sql or 'Not applicable.'})

Your task: Provide a single, comprehensive, and easy-to-understand answer to the user's CURRENT query: "{user_query}".
Integrate information naturally. Acknowledge errors/missing info briefly. Synthesize, do not just list. Be direct. Use history for context.

Final Comprehensive Answer:"""
        
        if orchestration_llm_instance:
            final_answer = orchestration_llm_instance._call(prompt=synthesis_prompt)
        else:
            final_answer = f"Doc Info: {rag_answer_text}\nDB Info: {sql_response_text}\n(Synthesis LLM N/A)"
    
    elif query_type == "UNKNOWN":
        final_answer = "I'm not sure how to answer that. Could you please provide more details or rephrase your question?"
    else: 
        final_answer = f"Unrecognized query type '{query_type}'. Please check logic."

    debug_info = f"Type: {query_type}. DocQ: {doc_question_decomposed}. DBQ: {db_question_decomposed}. RefinedDBQ: {current_db_question_for_sql if query_type=='HYBRID' else 'N/A'}"

    return {
        "answer": final_answer,
        "query_type_debug": query_type,
        "decomposed_doc_question_debug": doc_question_decomposed,
        "decomposed_db_question_debug": db_question_decomposed,
        "sources": sources, 
        "generated_sql": generated_sql, 
        "debug_info_orchestrator": debug_info,
        "error": None
    }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Testing hybrid_orchestrator_agent standalone with history...")
    
    example_history_1 = [
        {"sender": "user", "text": "What is our policy on inventory write-offs?"},
        {"sender": "ai", "text": "The policy includes several approval thresholds: Up to $5,000 by Department Manager, $5,001-$25,000 by Director of Operations, and above $25,000 by CEO/CFO."}
    ]
    test_query_1 = "And what products fall under the highest threshold and have been written off this year?"
    
    print(f"\n--- Test Query 1: '{test_query_1}' ---")
    result1 = run_hybrid_query(test_query_1, history=example_history_1)
    for key, value in result1.items():
        print(f"{key}: {value}")

    example_history_2 = [
        {"sender": "user", "text": "List orders from customer ID 791."},
        {"sender": "ai", "text": "Customer ID 791 (Mary Smith) has 5 orders with a total value of $9,436.61. Order IDs are O1, O2, O3, O4, O5."}
    ]
    test_query_2 = "Which of those orders were shipped late?"

    print(f"\n--- Test Query 2: '{test_query_2}' ---")
    result2 = run_hybrid_query(test_query_2, history=example_history_2)
    for key, value in result2.items():
        print(f"{key}: {value}")