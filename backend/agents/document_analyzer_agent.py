import os
import logging
# from crewai import Agent, Task, Crew, Process # Kept as per original file
# from crewai.tools import tool # Kept as per original file


import sys


# Get the absolute path of the project root (one level up from 'agents')
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)

from langchain_chroma import Chroma
from typing import List, Any, Dict

from core.hackathon_llms import SyngentaHackathonLLM, SyngentaHackathonEmbeddings
from config.settings import settings

logger = logging.getLogger(__name__)

# --- Initialize LLM for the Agent's own reasoning (CrewAI part, kept as per original) ---
reasoning_llm_instance = None
# try:
#     reasoning_llm_instance = SyngentaHackathonLLM(
#         model_id="claude-3.5-sonnet",
#         temperature=0.5,
#         max_tokens=3000
#     )
#     logger.info("Reasoning LLM (Claude 3.5 Sonnet) initialized for Agent's internal reasoning (CrewAI).")
# except Exception as e:
#     logger.error(f"Failed to initialize reasoning_llm_instance for DocumentAnalyzerAgent (CrewAI): {e}", exc_info=True)

# --- Initialize Embeddings client and Vector Store ---
embeddings_client = None
try:
    embeddings_client = SyngentaHackathonEmbeddings(model_id="amazon-embedding-v2")
    logger.info("Embeddings client initialized for document_analyzer_agent.")
except Exception as e:
    logger.error(f"Failed to initialize embeddings_client in document_analyzer_agent: {e}", exc_info=True)

vector_store = None
if embeddings_client:
    PROJECT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Assumes agents/ is one level down from project root
    persist_directory = os.path.join(PROJECT_BASE_DIR, settings.VECTOR_STORE_PATH)
    if os.path.exists(persist_directory):
        try:
            vector_store = Chroma(persist_directory=persist_directory, embedding_function=embeddings_client)
            logger.info(f"Chroma vector store loaded from: {persist_directory} in document_analyzer_agent.")
        except Exception as e:
            logger.error(f"Failed to load Chroma vector store in document_analyzer_agent: {e}", exc_info=True)
            vector_store = None
    else:
        logger.warning(f"Vector store persist directory not found: {persist_directory}. Run ingest_documents.py.")
else:
    logger.error("Embeddings client not initialized in document_analyzer_agent. Cannot load vector store.")


# --- Define the CORE LOGIC for the Tool (undecorated) (CrewAI part, kept as per original) ---
# def _core_answer_logic_for_tool(question_with_context: str) -> str:
#     logger.info(f"Tool's core logic _core_answer_logic_for_tool received input. Length: {len(question_with_context)}")
#     question_part = "Error: Could not parse question from tool input."
#     context_part = "Error: Could not parse context from tool input."
#     try:
#         q_marker_start = "USER QUESTION:"
#         c_marker_start = "CONTEXT:\n\"\"\""
#         c_marker_end = "\"\"\""
#         q_start_idx = question_with_context.find(q_marker_start)
#         c_start_idx = question_with_context.find(c_marker_start, q_start_idx if q_start_idx != -1 else 0)

#         if q_start_idx != -1 and c_start_idx != -1 and c_start_idx > q_start_idx:
#             question_part = question_with_context[q_start_idx + len(q_marker_start) : c_start_idx].strip()
#             context_content_start_idx = c_start_idx + len(c_marker_start)
#             context_end_idx = question_with_context.rfind(c_marker_end, context_content_start_idx)
#             if context_end_idx != -1 and context_end_idx > context_content_start_idx:
#                  context_part = question_with_context[context_content_start_idx : context_end_idx].strip()
#             else:
#                  context_part = question_with_context[context_content_start_idx:].strip()
#                  logger.warning("Tool core logic: Trailing '\"\"\"' for context was not found correctly or context was empty, took rest of string.")
#             logger.debug(f"Tool core logic parsed Question: {question_part[:100]}...")
#             logger.debug(f"Tool core logic parsed Context snippet: {context_part[:100]}...")
#         else:
#             raise ValueError("Input string not formatted correctly: Missing or misplaced USER QUESTION or CONTEXT markers.")
#     except Exception as e:
#         logger.error(f"Tool core logic failed to parse 'question_with_context'. Error: {e}. Input: {question_with_context[:300]}...")
#         return f"Error: Tool input malformed during parsing. Details: {str(e)}"
#     try:
#         qa_llm = SyngentaHackathonLLM(model_id="claude-3.5-sonnet", temperature=0.2, max_tokens=700)
#         tool_internal_prompt = (
#             f"Based ONLY on the following CONTEXT from company policy documents, answer the USER QUESTION.\n"
#             f"If the answer is not found in the CONTEXT, clearly state that 'The provided documents do not contain specific information about [topic of question]'.\n"
#             f"Do not use any external knowledge or make assumptions.\n"
#             f"Your answer should be concise and directly address the question.\n\n"
#             f"CONTEXT:\n\"\"\"\n{context_part}\n\"\"\"\n\n"
#             f"USER QUESTION: {question_part}\n\n"
#             f"ANSWER (provide only the answer text, no preamble about using context):"
#         )
#         response_text = qa_llm._call(prompt=tool_internal_prompt)
#         logger.info(f"Tool core logic's direct LLM call response snippet: {response_text[:100]}...")
#         return response_text
#     except Exception as e:
#         logger.error(f"Error in tool core logic's LLM call: {e}", exc_info=True)
#         return f"Error occurred within the tool's core logic while generating answer: {str(e)}"

# --- Wrap the core logic function into a CrewAI Tool (CrewAI part, kept as per original) ---
# @tool("AnswerFromContextTool")
# def get_answer_from_context_via_tool(question_with_context: str) -> str:
#     """
#     (Tool Description for the Agent)
#     Generates an answer to a user's question based on provided context.
#     The input 'question_with_context' MUST be a single string formatted exactly as:
#     "USER QUESTION: [The user's original question]\\nCONTEXT:\\n\"\"\"\\n[The retrieved document context]\\n\"\"\""
#     This tool will parse the question and context from this single string, then use an LLM to generate an answer based ONLY on the provided context.
#     If the answer cannot be found in the context, it will state that.
#     """
#     return _core_answer_logic_for_tool(question_with_context)

# --- Define the RAG Agent (CrewAI part, kept as per original) ---
# document_qa_agent = None
# if reasoning_llm_instance and get_answer_from_context_via_tool:
#     document_qa_agent = Agent(
#         role='Policy Document Specialist and Question Answering Expert',
#         goal=(
#             "Retrieve relevant information from policy documents by performing a semantic search. "
#             "Then, using the retrieved context and the original user question, utilize the 'AnswerFromContextTool' "
#             "to generate an accurate answer. If the information is not found, explicitly state that. "
#             "Finally, present the answer followed by a list of the source document filenames."
#         ),
#         backstory=(
#             "You are an AI assistant skilled in understanding user queries and finding information in company policy documents. "
#             "You first search for relevant document excerpts. Then, you use a special tool, 'AnswerFromContextTool', "
#             "to formulate an answer based *only* on those excerpts and the user's question. You always cite your sources clearly."
#         ),
#         verbose=True,
#         allow_delegation=False,
#         llm=reasoning_llm_instance,
#         tools=[get_answer_from_context_via_tool]
#     )
# else:
#     logger.warning("Document Q&A Agent (CrewAI) not created: 'reasoning_llm_instance' or 'get_answer_from_context_via_tool' tool is not available.")


# --- run_document_rag_query_direct function (MODIFIED) ---
def run_document_rag_query_direct(user_query: str) -> Dict[str, Any]:
    """
    Performs a RAG query: retrieves relevant documents,
    then uses SyngentaHackathonLLM to answer.
    Now also returns the raw retrieved context.
    """
    if not vector_store:
        logger.error("Vector store is not available for direct RAG. Run document ingestion first.")
        return {
            "answer": "Error: Vector store is not available. Please run document ingestion.",
            "raw_context": None,
            "sources": []
        }
    # API key/URL are handled by SyngentaHackathonLLM using settings.
    # No need to check settings.SYNGENTA_HACKATHON_API_KEY here.

    logger.info(f"Performing DIRECT RAG for query: '{user_query}'")

    retrieved_docs: List[Any] = []
    try:
        logger.debug("Retrieving relevant document chunks from vector store...")
        if hasattr(vector_store, 'similarity_search'):
            retrieved_docs = vector_store.similarity_search(user_query, k=3)
        else:
            logger.error("vector_store object does not have 'similarity_search' method or is not initialized.")
            # This indicates a problem with vector_store initialization earlier in the file.
            raise AttributeError("vector_store does not have 'similarity_search' method or is not initialized.")


        if not retrieved_docs:
            logger.warning("No relevant document chunks found for the query.")
            return {
                "answer": "I could not find relevant information in the policy documents for your query.",
                "raw_context": None,
                "sources": []
            }
        logger.info(f"Retrieved {len(retrieved_docs)} chunks for the query.")
    except Exception as e:
        logger.error(f"Error during document retrieval: {e}", exc_info=True)
        return {
            "answer": "Error: Failed to retrieve documents from the vector store.",
            "raw_context": None,
            "sources": []
        }

    context_str = "\n\n---\n\n".join([doc.page_content for doc in retrieved_docs])
    sources = sorted(list(set([doc.metadata.get("source", "Unknown Source") for doc in retrieved_docs])))

    llm_generated_answer = "Error: LLM call for Q&A did not complete."
    try:
        qa_llm = SyngentaHackathonLLM(
            model_id="claude-3.5-sonnet",
            temperature=0.2,
            max_tokens=700
        )
        
        final_prompt_for_llm = (
            f"Based ONLY on the following CONTEXT from company policy documents, answer the USER QUESTION.\n"
            f"If the answer is not found in the CONTEXT, clearly state that 'The provided documents do not contain specific information regarding your query on this topic'.\n"
            f"Do not use any external knowledge or make assumptions.\n"
            f"Your answer should be concise and directly address the question.\n\n"
            f"CONTEXT:\n\"\"\"\n{context_str}\n\"\"\"\n\n"
            f"USER QUESTION: {user_query}\n\n"
            f"ANSWER (provide only the answer text, no preamble about using context):"
        )
        
        logger.info("Calling SyngentaHackathonLLM directly for final answer generation...")
        llm_generated_answer_raw = qa_llm._call(prompt=final_prompt_for_llm)
        
        # Check for API errors (as per SyngentaHackathonLLM's _call method error returns)
        if "Error from API:" in llm_generated_answer_raw or \
           "Error: API request failed" in llm_generated_answer_raw or \
           "Error: Could not parse LLM response structure" in llm_generated_answer_raw or \
           "Error: API request timed out" in llm_generated_answer_raw or \
           "Error: Unexpected issue" in llm_generated_answer_raw: # Added another common error string
            logger.error(f"LLM call for Q&A failed or returned error string: {llm_generated_answer_raw}")
            llm_generated_answer = f"There was an issue generating the answer from the documents: {llm_generated_answer_raw}"
        else:
            logger.info(f"Successfully generated answer directly. Snippet: {llm_generated_answer_raw[:100]}...")
            llm_generated_answer = llm_generated_answer_raw
            
        return {
            "answer": llm_generated_answer,
            "raw_context": context_str,
            "sources": sources
        }

    except Exception as e:
        logger.error(f"Error during direct LLM call for Q&A in RAG: {e}", exc_info=True)
        return {
            "answer": f"An error occurred while generating the answer from documents: {str(e)}",
            "raw_context": context_str, # Context was retrieved before LLM call
            "sources": sources
        }

# --- Main block for testing (kept as per original, now reflects new return structure) ---
if __name__ == '__main__':
    # This block needs .env to be loaded for settings (API keys, paths)
    # Ensure PROJECT_BASE_DIR is correct if running this script directly
    # For example, if agents/ is in SYNGENTA_AI_AGENT/agents/
    if not embeddings_client or not vector_store: # Try to re-init if module-level failed
        logger.info("Attempting to re-initialize embeddings/vector_store for __main__ test.")
        try:
            if not embeddings_client:
                embeddings_client = SyngentaHackathonEmbeddings(model_id="amazon-embedding-v2")
                logger.info("Embeddings client re-initialized for test.")
            if embeddings_client and not vector_store:
                PROJECT_BASE_DIR_MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                persist_directory_main = os.path.join(PROJECT_BASE_DIR_MAIN, settings.VECTOR_STORE_PATH)
                if os.path.exists(persist_directory_main):
                    vector_store = Chroma(persist_directory=persist_directory_main, embedding_function=embeddings_client)
                    logger.info(f"Chroma vector store re-loaded for test from: {persist_directory_main}")
                else:
                    logger.error(f"Vector store path not found for re-init: {persist_directory_main}")
        except Exception as e_init:
            logger.error(f"Error during re-initialization for test: {e_init}")


    if not vector_store:
        logger.error("Cannot run direct RAG tests: Vector store not loaded.")
    else:
        logger.info("Proceeding with DIRECT RAG tests.")
        test_queries = [
            "According to our Transportation and Logistics policy, are we using the optimal shipping modes for high-value orders to international destinations?",
            "Based on our Risk Management framework, which supply chain disruptions occurred in the past year that exceeded our defined risk tolerance thresholds, and what was their financial impact?",
            "What is our company's definition of slow-moving inventory according to the Inventory Management policy?"
        ]
        for i, test_query in enumerate(test_queries):
            logger.info(f"\n--- ({i+1}/{len(test_queries)}) TESTING DIRECT RAG WITH QUERY: '{test_query}' ---")
            result = run_document_rag_query_direct(test_query)
            print(f"\n--- ({i+1}) Direct RAG Test Result ---")
            print(f"Query: {test_query}")
            print(f"LLM Answer:\n{result.get('answer')}")
            print(f"Raw Context (first 200 chars):\n{result.get('raw_context', '')[:200]}...")
            print(f"Retrieved Sources: {result.get('sources')}")
            print("-------------------------------------------\n")
    logger.info("--- All tests in document_analyzer_agent.py (direct RAG) finished ---")