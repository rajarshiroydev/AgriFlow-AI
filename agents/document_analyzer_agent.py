# SYNGENTA_AI_AGENT/agents/document_analyzer_agent.py
import os
import logging
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool 
from langchain_chroma import Chroma # Assuming updated Chroma import
from typing import List, Any, Dict

# Custom LLM and Embeddings for the hackathon API
from core.hackathon_llms import SyngentaHackathonLLM, SyngentaHackathonEmbeddings
from config.settings import settings

logger = logging.getLogger(__name__)

# --- Initialize LLM for the Agent's own reasoning ---
reasoning_llm_instance = None
try:
    reasoning_llm_instance = SyngentaHackathonLLM(
        model_id="claude-3.5-sonnet", # USING CLAUDE SONNET FOR AGENT REASONING
        temperature=0.5,
        max_tokens=3000 # Increased max_tokens for reasoning thought process
    )
    logger.info("Reasoning LLM (Claude 3.5 Sonnet) initialized for Agent's internal reasoning.")
except Exception as e:
    logger.error(f"Failed to initialize reasoning_llm_instance for DocumentAnalyzerAgent: {e}", exc_info=True)

# --- Initialize Embeddings client and Vector Store ---
embeddings_client = None
try:
    embeddings_client = SyngentaHackathonEmbeddings(model_id="amazon-embedding-v2")
    logger.info("Embeddings client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize embeddings_client: {e}", exc_info=True)

vector_store = None
if embeddings_client:
    PROJECT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    persist_directory = os.path.join(PROJECT_BASE_DIR, settings.VECTOR_STORE_PATH)
    if os.path.exists(persist_directory):
        try:
            vector_store = Chroma(persist_directory=persist_directory, embedding_function=embeddings_client)
            logger.info(f"Chroma vector store loaded from: {persist_directory}")
        except Exception as e:
            logger.error(f"Failed to load Chroma vector store: {e}", exc_info=True)
            vector_store = None
    else:
        logger.warning(f"Vector store persist directory not found: {persist_directory}. Run ingest_documents.py.")
else:
    logger.error("Embeddings client not initialized. Cannot load vector store.")

# --- Define the CORE LOGIC for the Tool (undecorated) ---
def _core_answer_logic_for_tool(question_with_context: str) -> str:
    logger.info(f"Tool's core logic _core_answer_logic_for_tool received input. Length: {len(question_with_context)}")
    question_part = "Error: Could not parse question from tool input."
    context_part = "Error: Could not parse context from tool input."
    try:
        q_marker_start = "USER QUESTION:"
        c_marker_start = "CONTEXT:\n\"\"\""
        c_marker_end = "\"\"\""
        q_start_idx = question_with_context.find(q_marker_start)
        c_start_idx = question_with_context.find(c_marker_start, q_start_idx if q_start_idx != -1 else 0) 

        if q_start_idx != -1 and c_start_idx != -1 and c_start_idx > q_start_idx:
            question_part = question_with_context[q_start_idx + len(q_marker_start) : c_start_idx].strip()
            context_content_start_idx = c_start_idx + len(c_marker_start)
            context_end_idx = question_with_context.rfind(c_marker_end, context_content_start_idx)
            if context_end_idx != -1 and context_end_idx > context_content_start_idx:
                 context_part = question_with_context[context_content_start_idx : context_end_idx].strip()
            else:
                 context_part = question_with_context[context_content_start_idx:].strip()
                 logger.warning("Tool core logic: Trailing '\"\"\"' for context was not found correctly or context was empty, took rest of string.")
            logger.debug(f"Tool core logic parsed Question: {question_part[:100]}...")
            logger.debug(f"Tool core logic parsed Context snippet: {context_part[:100]}...")
        else:
            raise ValueError("Input string not formatted correctly: Missing or misplaced USER QUESTION or CONTEXT markers.")
    except Exception as e:
        logger.error(f"Tool core logic failed to parse 'question_with_context'. Error: {e}. Input: {question_with_context[:300]}...")
        return f"Error: Tool input malformed during parsing. Details: {str(e)}"
    try:
        qa_llm = SyngentaHackathonLLM(model_id="claude-3.5-sonnet", temperature=0.2, max_tokens=700) 
        tool_internal_prompt = (
            f"Based ONLY on the following CONTEXT from company policy documents, answer the USER QUESTION.\n"
            f"If the answer is not found in the CONTEXT, clearly state that 'The provided documents do not contain specific information about [topic of question]'.\n"
            f"Do not use any external knowledge or make assumptions.\n"
            f"Your answer should be concise and directly address the question.\n\n"
            f"CONTEXT:\n\"\"\"\n{context_part}\n\"\"\"\n\n"
            f"USER QUESTION: {question_part}\n\n"
            f"ANSWER (provide only the answer text, no preamble about using context):"
        )
        response_text = qa_llm._call(prompt=tool_internal_prompt)
        logger.info(f"Tool core logic's direct LLM call response snippet: {response_text[:100]}...")
        return response_text
    except Exception as e:
        logger.error(f"Error in tool core logic's LLM call: {e}", exc_info=True)
        return f"Error occurred within the tool's core logic while generating answer: {str(e)}"

# --- Wrap the core logic function into a CrewAI Tool ---
@tool("AnswerFromContextTool")
def get_answer_from_context_via_tool(question_with_context: str) -> str:
    """
    (Tool Description for the Agent)
    Generates an answer to a user's question based on provided context.
    The input 'question_with_context' MUST be a single string formatted exactly as:
    "USER QUESTION: [The user's original question]\\nCONTEXT:\\n\"\"\"\\n[The retrieved document context]\\n\"\"\""
    This tool will parse the question and context from this single string, then use an LLM to generate an answer based ONLY on the provided context.
    If the answer cannot be found in the context, it will state that.
    """
    return _core_answer_logic_for_tool(question_with_context)

# --- Define the RAG Agent ---
document_qa_agent = None
if reasoning_llm_instance and get_answer_from_context_via_tool:
    document_qa_agent = Agent(
        role='Policy Document Specialist and Question Answering Expert',
        goal=(
            "Retrieve relevant information from policy documents by performing a semantic search. "
            "Then, using the retrieved context and the original user question, utilize the 'AnswerFromContextTool' "
            "to generate an accurate answer. If the information is not found, explicitly state that. "
            "Finally, present the answer followed by a list of the source document filenames."
        ),
        backstory=(
            "You are an AI assistant skilled in understanding user queries and finding information in company policy documents. "
            "You first search for relevant document excerpts. Then, you use a special tool, 'AnswerFromContextTool', "
            "to formulate an answer based *only* on those excerpts and the user's question. You always cite your sources clearly."
        ),
        verbose=True, 
        allow_delegation=False,
        llm=reasoning_llm_instance, # Uses Sonnet now
        tools=[get_answer_from_context_via_tool] 
    )
else:
    logger.warning("Document Q&A Agent not created: 'reasoning_llm_instance' or 'get_answer_from_context_via_tool' tool is not available.")

# --- run_document_rag_query function ---
def run_document_rag_query_direct(user_query: str) -> Dict[str, Any]: # Renamed for clarity
    """
    Performs a RAG query directly: retrieves relevant documents, 
    then uses SyngentaHackathonLLM to answer.
    """
    if not vector_store: # Check vector_store directly
        logger.error("Vector store is not available for direct RAG. Run document ingestion first.")
        return {"answer": "Error: Vector store is not available. Please run document ingestion.", "sources": []}
    if not settings.SYNGENTA_HACKATHON_API_KEY or not settings.SYNGENTA_HACKATHON_API_BASE_URL:
        logger.error("Hackathon API key or base URL is missing in settings for direct RAG.")
        return {"answer": "Error: API configuration missing.", "sources": []}

    logger.info(f"Performing DIRECT RAG for query: '{user_query}'")

    # 1. Retrieve relevant document chunks
    try:
        logger.debug("Retrieving relevant document chunks from vector store...")
        retrieved_docs = vector_store.similarity_search(user_query, k=3)
        if not retrieved_docs:
            logger.warning("No relevant document chunks found for the query.")
            return {"answer": "I could not find relevant information in the policy documents for your query.", "sources": []}
        logger.info(f"Retrieved {len(retrieved_docs)} chunks for the query.")
    except Exception as e:
        logger.error(f"Error during document retrieval: {e}", exc_info=True)
        return {"answer": "Error: Failed to retrieve documents from the vector store.", "sources": []}

    context_str = "\n\n---\n\n".join([doc.page_content for doc in retrieved_docs])
    sources = sorted(list(set([doc.metadata.get("source", "Unknown Source") for doc in retrieved_docs])))

    # 2. Call SyngentaHackathonLLM directly for Q&A
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
        answer_text = qa_llm._call(prompt=final_prompt_for_llm)
        
        if "Error from API:" in answer_text or "Error: API request failed" in answer_text or "Error: Could not parse" in answer_text:
            logger.error(f"LLM call for Q&A failed or returned error: {answer_text}")
            # Fallback or reformat error
            final_response = f"There was an issue generating the answer: {answer_text}"
        else:
            logger.info(f"Successfully generated answer directly. Snippet: {answer_text[:100]}...")
            final_response = f"{answer_text}\nSources: {', '.join(sources)}"
            
        return {"answer": final_response, "sources": sources}

    except Exception as e:
        logger.error(f"Error during direct LLM call for Q&A in RAG: {e}", exc_info=True)
        return {"answer": f"An error occurred while generating the answer: {str(e)}", "sources": sources}

# --- Main block for testing ---
if __name__ == '__main__':
    # ... (dotenv loading as before) ...
    # ... (direct tests for SyngentaHackathonLLM and Embeddings from hackathon_llms.py can be moved here or kept separate)

    if not vector_store:
        logger.error("Cannot run direct RAG tests: Vector store not loaded.")
    else:
        logger.info("Proceeding with DIRECT RAG tests (no CrewAI Agent for this part).")
        test_queries = [
            "What is the company policy on inventory write-offs?",
            "What are the guidelines for ethical sourcing?",
            "Tell me about the company's marketing strategy for lunar new year."
        ]
        for i, test_query in enumerate(test_queries):
            logger.info(f"\n--- ({i+1}/{len(test_queries)}) TESTING DIRECT RAG WITH QUERY: '{test_query}' ---")
            result = run_document_rag_query_direct(test_query) # Call the new direct function
            print(f"\n--- ({i+1}) Direct RAG Test Result ---")
            print(f"Query: {test_query}")
            print(f"Full Response:\n{result.get('answer')}") 
            # 'sources' is now part of the 'answer' string, but good to have it separately too.
            print(f"Retrieved Sources (for verification): {result.get('sources')}")
            print("-------------------------------------------\n")
    logger.info("--- All tests in document_analyzer_agent.py (direct RAG) finished ---")