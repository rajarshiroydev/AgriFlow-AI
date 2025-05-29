# Script to process policy docs and create/populate vector store

# SYNGENTA_AI_AGENT/scripts/ingest_documents.py
import os
import logging
from typing import List, Any


from langchain_community.document_loaders import PyPDFium2Loader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

# Custom Embeddings class for the hackathon API
from core.hackathon_llms import SyngentaHackathonEmbeddings
from config.settings import settings # For paths and API details (indirectly via hackathon_llms)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Determine project base directory to reliably find data folder
# Assumes this script is in SYNGENTA_AI_AGENT/scripts/
PROJECT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

POLICY_DOCS_PATH = os.path.join(PROJECT_BASE_DIR, "data", "raw", "dataco-global-policy-dataset")
CHROMA_PERSIST_DIR = os.path.join(PROJECT_BASE_DIR, settings.VECTOR_STORE_PATH) # Use path from settings

def load_and_split_pdfs(docs_path: str) -> List[Any]: # Returns List of LangChain Document objects
    """Loads all PDFs from a directory and splits them into chunks."""
    all_loaded_documents = [] # Store LangChain Document objects
    if not os.path.isdir(docs_path):
        logger.error(f"Policy documents path not found or not a directory: {docs_path}")
        return []

    logger.info(f"Loading PDF documents from: {docs_path}")
    pdf_files_found = 0
    for filename in os.listdir(docs_path):
        if filename.lower().endswith(".pdf"):
            pdf_files_found +=1
            file_path = os.path.join(docs_path, filename)
            try:
                logger.debug(f"Processing file: {filename}")
                loader = PyPDFium2Loader(file_path)
                # loader.load() returns a list of Document objects, often one per page.
                documents_from_pdf = loader.load()
                
                if documents_from_pdf:
                    # Add source metadata to each Document object
                    for doc_page in documents_from_pdf:
                        doc_page.metadata["source"] = filename # Original filename
                        doc_page.metadata["file_path"] = file_path # Full path if needed
                    all_loaded_documents.extend(documents_from_pdf)
                    logger.info(f"Successfully loaded {len(documents_from_pdf)} page(s) from {filename}.")
                else:
                    logger.warning(f"No content loaded from {filename}")
            except Exception as e:
                logger.error(f"Failed to load or process {filename}: {e}", exc_info=True)
    
    if not pdf_files_found:
        logger.error(f"No PDF files found in directory: {docs_path}")
        return []
    if not all_loaded_documents:
        logger.warning("No documents were loaded successfully. Exiting splitting process.")
        return []

    logger.info(f"Successfully loaded content from {len(all_loaded_documents)} document pages across all PDFs.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        add_start_index=True,
    )
    
    logger.info(f"Splitting {len(all_loaded_documents)} document pages into smaller text chunks...")
    chunked_documents = text_splitter.split_documents(all_loaded_documents)
    logger.info(f"Created {len(chunked_documents)} text chunks from the documents.")
    
    return chunked_documents


def initialize_embeddings_client() -> SyngentaHackathonEmbeddings:
    """Initializes and returns the Syngenta Hackathon Embeddings client."""
    logger.info("Initializing Syngenta Hackathon Embeddings (using amazon-embedding-v2 via custom API)...")
    try:
        # The custom class will pull API key and URL from settings via its default_factory
        embeddings_client = SyngentaHackathonEmbeddings(model_id="amazon-embedding-v2") # Ensure this model_id is correct
        logger.info("Syngenta Hackathon Embeddings client initialized successfully.")
        return embeddings_client
    except Exception as e:
        logger.error(f"Failed to initialize SyngentaHackathonEmbeddings: {e}", exc_info=True)
        raise # Re-raise to stop the script if embeddings can't be initialized


def create_and_persist_vector_store(documents: List[Any], embeddings_client: SyngentaHackathonEmbeddings, persist_directory: str):
    """Creates a Chroma vector store from documents and embeddings, and persists it."""
    if not documents:
        logger.warning("No documents provided to create vector store. Skipping.")
        return None

    logger.info(f"Ensuring Chroma persist directory exists: {persist_directory}")
    os.makedirs(persist_directory, exist_ok=True)

    logger.info(f"Creating/updating Chroma vector store. Number of document chunks: {len(documents)}.")
    try:
        # If the directory is not empty, Chroma will try to load an existing DB.
        # If you want to overwrite or ensure a fresh build, you might need to clear the directory first.
        # For this script, let's assume we are adding to or creating new.
        vector_db = Chroma.from_documents(
            documents=documents,
            embedding=embeddings_client,
            persist_directory=persist_directory
        )
        # No explicit vector_db.persist() is typically needed with Chroma.from_documents when persist_directory is set,
        # as it writes as it goes. However, calling it doesn't hurt and ensures everything is flushed.
        logger.info("Persisting vector store changes (if any)...")
        #vector_db.persist() 
        logger.info(f"Successfully created/updated and persisted Chroma vector store at {persist_directory}")
        return vector_db
    except Exception as e:
        logger.error(f"Failed to create or persist Chroma vector store: {e}", exc_info=True)
        return None

def main_ingestion():
    logger.info("Starting document ingestion process for Syngenta Hackathon...")
    
    chunked_docs = load_and_split_pdfs(POLICY_DOCS_PATH)
    if not chunked_docs:
        logger.error("No document chunks were created. Halting ingestion.")
        return

    try:
        embeddings_client = initialize_embeddings_client()
    except Exception:
        logger.error("Failed to initialize embeddings model. Halting ingestion.")
        return

    vector_store = create_and_persist_vector_store(chunked_docs, embeddings_client, CHROMA_PERSIST_DIR)

    if vector_store:
        logger.info("Document ingestion process completed successfully!")
        # You can add a test query here if desired
        # try:
        #     logger.info("Performing a test similarity search...")
        #     results = vector_store.similarity_search("inventory write-off policy", k=2)
        #     for doc in results:
        #         logger.info(f"Found in {doc.metadata.get('source', 'N/A')}: {doc.page_content[:100]}...")
        # except Exception as e:
        #     logger.error(f"Test query failed: {e}")
    else:
        logger.error("Document ingestion process failed to create or persist the vector store.")

if __name__ == "__main__":
    # This ensures .env is loaded if script is run directly (python scripts/ingest_documents.py)
    # It's less critical if run via `docker exec` as docker-compose handles .env loading.
    env_path = os.path.join(PROJECT_BASE_DIR, '.env')
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        logger.info(f"Loading .env file from: {env_path}")
        load_dotenv(dotenv_path=env_path)
    else:
        logger.warning(f".env file not found at {env_path}. Relying on existing environment variables.")
        
    main_ingestion()