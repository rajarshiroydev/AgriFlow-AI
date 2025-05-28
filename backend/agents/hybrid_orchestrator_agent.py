# SYNGENTA_AI_AGENT/agents/hybrid_orchestrator_agent.py

import logging
import json
import re 
from typing import Dict, Any, Optional, List

import sys
import os
PROJECT_ROOT_FOR_HYBRID = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT_FOR_HYBRID not in sys.path:
    sys.path.append(PROJECT_ROOT_FOR_HYBRID)

from core.hackathon_llms import SyngentaHackathonLLM
from agents.document_analyzer_agent import run_document_rag_query_direct
from agents.sql_query_agent import execute_natural_language_sql_query
from core.access_control import check_query_access # <<< NEW IMPORT
from core.access_profiles import DEFAULT_USER_ID   # <<< NEW IMPORT

logger = logging.getLogger(__name__)

orchestration_llm_instance: Optional[SyngentaHackathonLLM] = None
try:
    orchestration_llm_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", 
        temperature=0.1, 
        max_tokens=2500 
    )
    logger.info("Orchestration LLM initialized for Hybrid Orchestrator.")
except Exception as e:
    logger.error(f"Failed to initialize orchestration_llm_instance for Hybrid Orchestrator: {e}", exc_info=True)

def _format_history_for_prompt(history: Optional[List[Any]], max_turns: int = 3) -> str:
    if not history: return "No conversation history provided."
    effective_history = history[-(max_turns * 2):] 
    if not effective_history: return "No recent conversation history to display."
    formatted_history_lines = ["Previous conversation turns (most recent last):"]
    for msg_obj in effective_history: 
        sender = msg_obj.sender.capitalize() 
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

Based on the user's CURRENT question, provide a JSON response:
{{
  "query_type": "DOCUMENT_ONLY" | "DATABASE_ONLY" | "HYBRID" | "UNKNOWN",
  "document_question": "The specific question for policy documents. (String or null)",
  "database_question": "The specific question for the structured database. (String or null)",
  "original_query": "The original CURRENT user query."
}}
Focus on resolving the CURRENT query using history for context.
If HYBRID, formulate sub-questions. If UNKNOWN, state so.

CURRENT User Query: "{user_query_placeholder}"
JSON Response:"""

def _decompose_query_intent(user_query: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
    if not orchestration_llm_instance: logger.error("Orchestration LLM not initialized."); return None
    formatted_history = _format_history_for_prompt(history)
    prompt = QUERY_DECOMPOSITION_PROMPT_TEMPLATE.format(
        conversation_history_placeholder=formatted_history, user_query_placeholder=user_query
    )
    logger.info(f"Decomposing query: '{user_query}' (History: {len(history) if history else 0})")
    try:
        response_text = orchestration_llm_instance._call(prompt=prompt)
        parsed_json = None 
        try:
            json_block_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text, re.DOTALL)
            if json_block_match: json_str = json_block_match.group(1).strip(); parsed_json = json.loads(json_str)
            else:
                start_brace = response_text.find('{'); end_brace = response_text.rfind('}')
                if start_brace!=-1 and end_brace!=-1 and end_brace > start_brace: parsed_json = json.loads(response_text[start_brace:end_brace+1])
                else: parsed_json = json.loads(response_text)
        except json.JSONDecodeError as e_json: logger.error(f"JSON parse error: {e_json}. Response: {response_text[:500]}"); return None
        if parsed_json is None: logger.error(f"JSON parsing resulted in None. LLM response: {response_text[:500]}"); return None
        required_keys = {"query_type", "document_question", "database_question", "original_query"}
        if not required_keys.issubset(parsed_json.keys()): logger.error(f"Parsed JSON missing keys: {required_keys - set(parsed_json.keys())}. Parsed: {parsed_json}"); return None
        logger.info(f"Decomposed query. Type: {parsed_json.get('query_type')}")
        return parsed_json
    except Exception as e: logger.error(f"Decomposition LLM call error: {e}", exc_info=True); return None

def _refine_db_question_with_context(original_db_question: Optional[str], document_context: Optional[str], original_user_query: str ) -> Optional[str]:
    if not original_db_question: return None
    meaningless_contexts = ["No raw document context retrieved.","Failed to get raw document context from RAG.","No document retrieval was performed as no document question was identified."]
    if not document_context or document_context.strip()=="" or document_context in meaningless_contexts: return original_db_question
    if not orchestration_llm_instance: return original_db_question
    logger.info(f"Refining DB question: '{original_db_question}' for user query: '{original_user_query}'")
    truncated_doc_context = str(document_context)[:2000]
    refinement_prompt = f"""User's query: "{original_user_query}"
Database part: "{original_db_question}"
Document context: ---START--- {truncated_doc_context} ---END---
Refine the "database part" using specific definitions/criteria from "document context" for a SQL query. If no refinement applicable or context unhelpful, return the original "database part" EXACTLY.
Refined Database Question:"""
    try:
        refined_q = orchestration_llm_instance._call(prompt=refinement_prompt).strip()
        if not refined_q: return original_db_question
        if refined_q.lower()!=original_db_question.lower(): logger.info(f"Refined DB Q: '{refined_q}' (Original: '{original_db_question}')")
        return refined_q
    except Exception as e: logger.error(f"Refinement LLM error: {e}", exc_info=True); return original_db_question

def run_hybrid_query(user_query: str, history: Optional[List[Dict[str, str]]] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    effective_user_id = user_id if user_id and user_id.strip() else DEFAULT_USER_ID
    logger.info(f"Hybrid query: '{user_query}' (User: {effective_user_id}, History: {len(history) if history else 0})")
    
    sources: List[str] = []
    generated_sql: Optional[str] = None
    final_answer: str = "Processing..."
    current_db_question_for_sql: Optional[str] = None # Initialize here for broader scope

    decomposed_intent = _decompose_query_intent(user_query, history)

    if not decomposed_intent:
        return {"answer": "I had trouble understanding your request.", "query_type_debug": "DECOMPOSITION_FAILED", "decomposed_doc_question_debug": None, "decomposed_db_question_debug": None, "sources": [], "generated_sql": None, "debug_info_orchestrator": "Query decomposition failed.", "error": "Query decomposition failed."}

    query_type = decomposed_intent.get("query_type")
    doc_question = decomposed_intent.get("document_question")
    db_question = decomposed_intent.get("database_question")
    original_query_from_decomp = decomposed_intent.get("original_query", user_query)
    
    if not check_query_access(effective_user_id, user_query, db_question, doc_question):
        return {
            "answer": "I'm sorry, but you do not have sufficient permissions to access the information for this query.",
            "query_type_debug": query_type, "decomposed_doc_question_debug": doc_question,
            "decomposed_db_question_debug": db_question, "sources": [], "generated_sql": None,
            "debug_info_orchestrator": f"Access denied for user {effective_user_id}.", "error": "Access Denied"
        }

    rag_answer_text = "No document information was sought or retrieved."
    raw_doc_context_for_synthesis = "No document retrieval was performed."
    sql_response_text = "No database information was sought or retrieved."
    current_db_question_for_sql = db_question

    if query_type == "DOCUMENT_ONLY":
        if doc_question:
            rag_result = run_document_rag_query_direct(doc_question)
            final_answer = rag_result.get("answer", "No answer found from documents.")
            sources = rag_result.get("sources", [])
        else: final_answer = "Document question expected but not formed."

    elif query_type == "DATABASE_ONLY":
        if db_question:
            sql_result = execute_natural_language_sql_query(db_question, user_id=effective_user_id)
            final_answer = sql_result.get("answer", "No answer found from database.")
            generated_sql = sql_result.get("generated_sql")
            if sql_result.get("error"): final_answer += f" (DB Error: {sql_result.get('error')})"
        else: final_answer = "Database question expected but not formed."
        
    elif query_type == "HYBRID":
        if doc_question:
            rag_result = run_document_rag_query_direct(doc_question)
            rag_answer_text = rag_result.get("answer", "Could not retrieve document context.")
            raw_doc_context_for_synthesis = rag_result.get("raw_context", "Failed to get raw document context.")
            sources.extend(rag_result.get("sources", []))
        
        current_db_question_for_sql = db_question # Initialize with the one from decomposition
        if db_question: 
            refined_db_q = _refine_db_question_with_context(
                db_question, raw_doc_context_for_synthesis, original_query_from_decomp 
            )
            if refined_db_q: current_db_question_for_sql = refined_db_q
        
        if current_db_question_for_sql: 
            sql_result = execute_natural_language_sql_query(current_db_question_for_sql, user_id=effective_user_id)
            sql_response_text = sql_result.get("answer", "Failed to get answer from database.")
            generated_sql = sql_result.get("generated_sql") 
            if sql_result.get("error"): sql_response_text += f" (DB Error: {sql_result.get('error')})"
        else:
             sql_response_text = "No database query was performed (no question after refinement)."
             if db_question: # Only set generated_sql if a db_question was initially present
                generated_sql = "Not applicable (DB question removed after refinement)."
             else:
                generated_sql = "Not applicable (no DB question)."


        formatted_history_for_synthesis = _format_history_for_prompt(history, max_turns=2)
        synthesis_prompt = f"""CONVERSATION HISTORY:\n{formatted_history_for_synthesis}\n\nUser's CURRENT query: "{user_query}"
To address CURRENT query:
1. Docs Q: "{doc_question or 'N/A'}" -> Doc Info: "{rag_answer_text}"
2. DB Q: "{current_db_question_for_sql or 'N/A'}" -> DB Info: "{sql_response_text}" (SQL: {generated_sql or 'N/A'})
Synthesize a comprehensive answer for the CURRENT query, using history for context. Be direct. Acknowledge errors.
Final Answer:"""
        
        if orchestration_llm_instance:
            final_answer = orchestration_llm_instance._call(prompt=synthesis_prompt)
        else:
            final_answer = f"Doc Info: {rag_answer_text}\nDB Info: {sql_response_text}\n(Synthesis LLM N/A)"
    
    elif query_type == "UNKNOWN":
        final_answer = "I'm not sure how to answer that. Could you rephrase?"
    else: 
        final_answer = f"Unrecognized query type '{query_type}'."

    debug_info_orchestrator = (
        f"User: {effective_user_id}. Type: {query_type}. "
        f"DecompDocQ: {doc_question}. DecompDbQ: {db_question}. "
        f"ActualDocQ: {doc_question if query_type != 'DATABASE_ONLY' else 'N/A'}. "
        f"ActualDbQ: {current_db_question_for_sql if query_type != 'DOCUMENT_ONLY' else 'N/A'}."
    )
    
    return {
        "answer": final_answer,
        "query_type_debug": query_type,
        "decomposed_doc_question_debug": doc_question,
        "decomposed_db_question_debug": db_question,
        "sources": sources, 
        "generated_sql": generated_sql, 
        "debug_info_orchestrator": debug_info_orchestrator,
        "error": None 
    }

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    test_scenarios = [
        {"user_id": "guest_global", "query": "What is the profit margin on our products?"},
        {"user_id": "analyst_us", "query": "What is the total sales in EMEA?"}, # Should be filtered or denied based on SQL agent's ability
        {"user_id": "analyst_us", "query": "What is the total sales?"}, # Should be filtered to US
        {"user_id": "manager_emea", "query": "Show me profit margins for all products."},
        {"user_id": "admin_global", "query": "What are the profit margins in the US region?"}
    ]

    for i, scenario in enumerate(test_scenarios):
        print(f"\n--- Scenario {i+1}: User '{scenario['user_id']}', Query: '{scenario['query']}' ---")
        result = run_hybrid_query(user_query=scenario["query"], user_id=scenario["user_id"])
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("-" * 40)