import logging
import os
import sys

# --- Add project root to sys.path ---
# This helps FastAPI/Uvicorn find your 'agents', 'core', 'config' modules
# when 'app.main:app' is run.
# The 'app' directory (where this main.py resides) is one level below the project root.
try:
    CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT_DIR = os.path.abspath(os.path.join(CURRENT_FILE_DIR, '..')) # Moves one level up to SYNGENTA_AI_AGENT/
    
    if PROJECT_ROOT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_ROOT_DIR) # Insert at the beginning to prioritize project modules
    
    # For debugging path issues:
    # print(f"DEBUG: [app/main.py] Current file directory: {CURRENT_FILE_DIR}")
    # print(f"DEBUG: [app/main.py] Calculated project root: {PROJECT_ROOT_DIR}")
    # print(f"DEBUG: [app/main.py] sys.path after modification: {sys.path}")

except Exception as e:
    # Fallback or critical error logging if path adjustment fails
    sys.stderr.write(f"CRITICAL ERROR: Failed to adjust sys.path in app/main.py: {e}\n")
    # Depending on the severity, you might want to exit or raise
    # For now, we'll let it try to proceed, but imports might fail.


# --- Configure basic logging ---
# This should be done before other modules (like your routers or agents) might try to log.
# It ensures logs are formatted and go to stdout, which is standard for Docker.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(), # Allow LOG_LEVEL override via env var
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)] # Explicitly stream to stdout
)
logger = logging.getLogger(__name__) # Get logger for this module


# --- Import FastAPI and other necessary modules AFTER path adjustment and logging setup ---
try:
    from fastapi import FastAPI
    from app.routers import chat_router # Your chat router
    from config.settings import settings # Your application settings
except ImportError as e_import:
    logger.critical(f"Failed to import core modules (FastAPI, routers, settings) in app/main.py: {e_import}", exc_info=True)
    logger.critical("This often indicates a PYTHONPATH issue or that the sys.path adjustment failed.")
    # Depending on policy, you might want to sys.exit(1) here if essential imports fail.
    # For now, raising it will stop the app from starting if FastAPI itself can't be imported.
    raise


# --- FastAPI App Instantiation ---
app = FastAPI(
    title="Syngenta AI Agent API",
    description=f"API for the Syngenta AI Agent Hackathon. Environment: {settings.ENVIRONMENT}",
    version="0.1.0",
    # You can customize OpenAPI URLs if needed, e.g., if behind a proxy with a path prefix
    # docs_url="/api/docs",
    # redoc_url="/api/redoc",
    # openapi_url="/api/openapi.json"
)

# --- Include Routers ---
# The prefix for routes (e.g., "/api/v1") is defined within the router itself (chat_router.py)
app.include_router(chat_router.router)


# --- FastAPI Event Handlers ---
@app.on_event("startup")
async def startup_event():
    logger.info("--- FastAPI Application Startup Sequence Initiated ---")
    logger.info(f"Application Title: {app.title}")
    logger.info(f"Application Version: {app.version}")
    logger.info(f"Operating Environment: {settings.ENVIRONMENT}")
    logger.info(f"Hackathon API Base URL: {settings.SYNGENTA_HACKATHON_API_BASE_URL}")
    
    api_key_status = "SET" if settings.SYNGENTA_HACKATHON_API_KEY and len(settings.SYNGENTA_HACKATHON_API_KEY) > 4 else "NOT SET or too short"
    logger.info(f"Syngenta Hackathon API Key Status: {api_key_status}")
    
    # Verify critical components or connections if necessary
    # Example: Check if vector store path from settings exists
    vector_store_full_path = os.path.join(PROJECT_ROOT_DIR, settings.VECTOR_STORE_PATH)
    if os.path.exists(vector_store_full_path):
        logger.info(f"Vector Store Path ({settings.VECTOR_STORE_PATH}) found at: {vector_store_full_path}")
    else:
        logger.warning(f"Vector Store Path ({settings.VECTOR_STORE_PATH}) NOT found at: {vector_store_full_path}. Document Q&A may fail.")
        
    logger.info("--- FastAPI Application Startup Complete ---")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("--- FastAPI Application Shutdown Sequence Initiated ---")
    # Add any cleanup tasks here (e.g., closing database connections if managed globally)
    logger.info("--- FastAPI Application Shutdown Complete ---")


# --- Root Endpoint ---
@app.get("/", tags=["Health Check"]) # Added a tag for better OpenAPI organization
async def read_root():
    """
    Root endpoint for the API.
    Provides a simple health check and welcome message, including the current environment.
    """
    return {
        "message": "Welcome to the Syngenta AI Agent API!",
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "docs_url": app.docs_url,
        "redoc_url": app.redoc_url
    }

# --- Main block for direct execution (less common for FastAPI, Uvicorn is preferred) ---
# Uvicorn is typically used to run the app, e.g., uvicorn app.main:app --reload
# Your project's root main.py (Typer CLI) already handles this.
if __name__ == "__main__":
    logger.warning("This FastAPI app (app/main.py) is being run directly. "
                   "It's recommended to use Uvicorn via the project's root main.py (Typer CLI) "
                   "or a direct Uvicorn command for production/development.")
    
    # This is just for basic testing if you were to run `python app/main.py`
    # Note: This won't have auto-reload or multiple workers like Uvicorn provides.
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)