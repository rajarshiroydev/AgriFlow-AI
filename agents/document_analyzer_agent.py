# For RAG on policy docs

# SYNGENTA_AI_AGENT/agents/document_analyzer_agent.py
import os
import logging
from crewai import Agent, Task, Crew, Process
from langchain_community.vectorstores import Chroma

# Custom LLM and Embeddings for the hackathon API
from core.hackathon_llms import SyngentaHackathonLLM, SyngentaHackathonEmbeddings
from config.settings import settings # For paths and API details

logger = logging.getLogger(__name__)

# Initialize LLM for the agent
try:
    # Using Claude 3.5 Sonnet as it's more capable for reasoning, via the hackathon API
    llm = SyngentaHackathonLLM(model_id="claude-3.5-sonnet", temperature=0.3) # Lower temp for factual retrieval
    logger.info("SyngentaHackathonLLM (Claude 3.5 Sonnet) initialized for DocumentAnalyzerAgent.")
except Exception as e:
    llm = None
    logger.error(f"Failed to initialize SyngentaHackathonLLM for DocumentAnalyzerAgent: {e}", exc_info=True)

# Initialize Embeddings client (needed to load the vector store)
try:
    embeddings_client = SyngentaHackathonEmbeddings(model_id="amazon-embedding-v2")
    logger.info("SyngentaHackathonEmbeddings initialized for loading vector store.")
except Exception as e:
    embeddings_client = None
    logger.error(f"Failed to initialize SyngentaHackathonEmbeddings for vector store: {e}", exc_info=True)

# Load the persisted vector store
vector_store = None
if embeddings_client:
    persist_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), settings.VECTOR_STORE_PATH)
    if os.path.exists(persist_directory):
        try:
            logger.info(f"Loading existing Chroma vector store from: {persist_directory}")
            vector_store = Chroma(
                persist_directory=persist_directory,
                embedding_function=embeddings_client
            )
            logger.info("Chroma vector store loaded successfully.")
            # Test query to ensure it's working
            # test_results = vector_store.similarity_search("test", k=1)
            # logger.info(f"Vector store test query returned {len(test_results)} result(s).")
        except Exception as e:
            logger.error(f"Failed to load Chroma vector store from {persist_directory}: {e}", exc_info=True)
            vector_store = None # Ensure it's None if loading failed
    else:
        logger.warning(f"Vector store persist directory not found: {persist_directory}. RAG will not work. Run ingest_documents.py first.")
else:
    logger.error("Embeddings client not initialized. Cannot load vector store.")


# Define the RAG Agent
document_qa_agent = None
if llm:
    document_qa_agent = Agent(
        role='Policy Document Specialist and Question Answering Expert',
        goal=(
            "Accurately answer user questions based SOLELY on the provided context from relevant policy document excerpts. "
            "If the answer is not found in the provided context, explicitly state that. "
            "Cite the source document(s) for your answer."
        ),
        backstory=(
            "You are an AI assistant highly skilled in information retrieval and natural language understanding. "
            "You have access to a collection of company policy documents. Your primary function is to find "
            "the most relevant information within these documents to answer user queries precisely and concisely, "
            "always indicating the source of the information."
        ),
        verbose=True,
        allow_delegation=False,
        llm=llm,
        # tools=[] # No external tools for this agent initially, context comes from retrieval
    )
else:
    logger.warning("Document Q&A Agent not created because LLM is not available.")


def run_document_rag_query(user_query: str) -> Dict[str, Any]:
    """
    Performs a RAG query: retrieves relevant documents, then uses an LLM to answer.
    """
    if not document_qa_agent:
        return {"answer": "Error: Document Q&A Agent is not initialized.", "sources": []}
    if not vector_store:
        return {"answer": "Error: Vector store is not available. Please run document ingestion.", "sources": []}

    logger.info(f"Performing RAG for query: '{user_query}'")

    # 1. Retrieve relevant document chunks
    try:
        logger.debug("Retrieving relevant document chunks from vector store...")
        # k=3 means retrieve top 3 most similar chunks
        retrieved_docs = vector_store.similarity_search(user_query, k=3) 
        if not retrieved_docs:
            logger.warning("No relevant document chunks found for the query.")
            return {"answer": "I could not find relevant information in the policy documents for your query.", "sources": []}
        
        logger.info(f"Retrieved {len(retrieved_docs)} chunks for the query.")
        for i, doc in enumerate(retrieved_docs):
            logger.debug(f"Chunk {i+1} (Source: {doc.metadata.get('source', 'N/A')}): {doc.page_content[:150]}...")

    except Exception as e:
        logger.error(f"Error during document retrieval: {e}", exc_info=True)
        return {"answer": "Error: Failed to retrieve documents from the vector store.", "sources": []}

    # 2. Construct context for the LLM
    context_str = "\n\n---\n\n".join([doc.page_content for doc in retrieved_docs])
    
    # Extract unique source filenames
    sources = list(set([doc.metadata.get("source", "Unknown Source") for doc in retrieved_docs]))

    # 3. Define the Task for the LLM Agent
    qa_task = Task(
        description=(
            f"Based ONLY on the following CONTEXT from company policy documents, answer the USER QUESTION.\n"
            f"If the answer is not found in the CONTEXT, clearly state that the information is not available in the provided documents.\n"
            f"Do not use any external knowledge or make assumptions.\n"
            f"After providing the answer, list the source document filenames as 'Sources: [filename1, filename2, ...]'.\n\n"
            f"CONTEXT:\n\"\"\"\n{context_str}\n\"\"\"\n\n"
            f"USER QUESTION: {user_query}"
        ),
        expected_output=(
            "A concise answer to the user's question based strictly on the provided context, "
            "followed by a list of source document names. For example: "
            "'The policy states X. Sources: [policy_A.pdf, policy_B.pdf]'. "
            "Or, 'The provided documents do not contain specific information about Y. Sources: [policy_C.pdf]'."
        ),
        agent=document_qa_agent
    )

    # 4. Create and run a temporary Crew for this RAG task
    # (Using a temporary crew is fine for single-shot RAG like this)
    temp_crew = Crew(
        agents=[document_qa_agent],
        tasks=[qa_task],
        process=Process.sequential,
        verbose=False # Set to True for more detailed CrewAI logs during execution
    )

    logger.info("Kicking off Document Q&A Crew...")
    try:
        # CrewAI kickoff doesn't take 'inputs' if they are already embedded in task description.
        result_obj = temp_crew.kickoff() 
        
        if result_obj and hasattr(result_obj, 'raw') and result_obj.raw:
            llm_response_text = result_obj.raw.strip()
            # We could try to parse out answer and sources more robustly here if needed
            # For now, we assume the LLM follows the prompt for structured output.
            logger.info(f"LLM Raw Response: {llm_response_text}")
            # Simple split for now, can be improved
            answer_part = llm_response_text
            parsed_sources = sources # Use sources from retrieval step for now
            
            # Attempt to find "Sources:" line and extract, if LLM includes it as instructed
            if "Sources:" in llm_response_text:
                parts = llm_response_text.split("Sources:", 1)
                answer_part = parts[0].strip()
                # Further parse sources from parts[1] if needed, but sources from retrieval is more reliable
                # For now, we'll just use the sources from retrieval
            
            return {"answer": answer_part, "sources": parsed_sources}

        elif result_obj: # If result_obj is not None but .raw is missing/empty
            logger.warning(f"Document Q&A Crew returned an object without a 'raw' attribute or it was empty: {result_obj}")
            return {"answer": "Received an empty or malformed response from the AI agent.", "sources": sources}
        else:
            logger.error("Document Q&A Crew kickoff returned None.")
            return {"answer": "Error: AI agent failed to generate a response.", "sources": sources}
            
    except Exception as e:
        logger.error(f"Error during Document Q&A Crew execution: {e}", exc_info=True)
        return {"answer": f"An error occurred while processing your query: {e}", "sources": []}

if __name__ == '__main__':
    # This is for local testing of this agent module
    # Ensure .env is loaded for settings
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        logger.info(f"Loading .env file from: {env_path} for document_analyzer_agent test.")
        load_dotenv(dotenv_path=env_path)
    else:
        logger.warning(f".env file not found at {env_path} for test. Relying on system environment variables.")

    if not vector_store:
        logger.error("Cannot run test: Vector store not loaded. Run 'scripts/ingest_documents.py' first.")
    else:
        test_query = "What is the company policy on inventory write-offs?"
        logger.info(f"\n--- TESTING RAG AGENT WITH QUERY: '{test_query}' ---")
        result = run_document_rag_query(test_query)
        print("\n--- RAG Agent Test Result ---")
        print(f"Query: {test_query}")
        print(f"Answer: {result.get('answer')}")
        print(f"Sources: {result.get('sources')}")
        print("-----------------------------")

        test_query_2 = "What are the guidelines for ethical sourcing?"
        logger.info(f"\n--- TESTING RAG AGENT WITH QUERY: '{test_query_2}' ---")
        result_2 = run_document_rag_query(test_query_2)
        print("\n--- RAG Agent Test Result ---")
        print(f"Query: {test_query_2}")
        print(f"Answer: {result_2.get('answer')}")
        print(f"Sources: {result_2.get('sources')}")
        print("-----------------------------")

        test_query_3 = "Tell me about the company's marketing strategy for lunar new year."
        logger.info(f"\n--- TESTING RAG AGENT WITH QUERY (EXPECT NO INFO): '{test_query_3}' ---")
        result_3 = run_document_rag_query(test_query_3)
        print("\n--- RAG Agent Test Result ---")
        print(f"Query: {test_query_3}")
        print(f"Answer: {result_3.get('answer')}")
        print(f"Sources: {result_3.get('sources')}")
        print("-----------------------------")