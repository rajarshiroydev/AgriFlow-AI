import logging
import os
import sys

# --- Add project root to sys.path ---
# This helps FastAPI/Uvicorn find your 'agents', 'core', 'config' modules
# when 'app.main:app' is run.
# The 'app' directory (where this main.py resides) is one level below the project root.
try:
    CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Assuming 'app' is a direct child of 'backend', and 'backend' is the project root for these modules.
    # If your main.py (Typer CLI) is in 'backend' and 'app' is 'backend/app',
    # then PROJECT_ROOT_DIR should point to 'backend'.
    # The Uvicorn command `uvicorn app.main:app` implies that Python's execution context
    # will be set up such that `app` is a top-level package.
    # The sys.path.insert(0, PROJECT_ROOT_DIR) in the FastAPI app's main.py
    # is primarily to ensure that when Uvicorn loads `app.main`, `app.main` itself can find
    # other top-level packages like `agents`, `core`, `config` if they are siblings to `app` dir.
    # If your structure is AGRIFLOW/backend/app/main.py and AGRIFLOW/backend/agents etc.,
    # then PROJECT_ROOT_DIR should be AGRIFLOW/backend.
    
    # Let's assume the structure AGRIFLOW/backend/ is where all Python packages (agents, app, core, config) live
    # and Uvicorn is run with `backend` as part of its python path implicitly or explicitly.
    # The sys.path modification helps if Uvicorn's default python path doesn't include the parent of 'app', 'agents', etc.
    # If 'app' is in 'AGRIFLOW/backend/app' and 'agents' is in 'AGRIFLOW/backend/agents',
    # then PROJECT_ROOT_DIR should be 'AGRIFLOW/backend'.
    PROJECT_ROOT_DIR_FOR_MODULES = os.path.abspath(os.path.join(CURRENT_FILE_DIR, '..')) # This goes up to 'backend'
    
    if PROJECT_ROOT_DIR_FOR_MODULES not in sys.path:
        sys.path.insert(0, PROJECT_ROOT_DIR_FOR_MODULES)
    
except Exception as e:
    sys.stderr.write(f"CRITICAL ERROR: Failed to adjust sys.path in app/main.py: {e}\n")


# --- Configure basic logging ---
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# --- Import FastAPI and other necessary modules AFTER path adjustment and logging setup ---
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
    from app.routers import chat_router # Your chat router
    from config.settings import settings # Your application settings
except ImportError as e_import:
    logger.critical(f"Failed to import core modules (FastAPI, routers, settings) in app/main.py: {e_import}", exc_info=True)
    logger.critical("This often indicates a PYTHONPATH issue or that the sys.path adjustment failed.")
    raise


# --- FastAPI App Instantiation ---
app = FastAPI(
    title="Syngenta AI Agent API",
    description=f"API for the Syngenta AI Agent Hackathon. Environment: {settings.ENVIRONMENT}",
    version="0.1.0",
    # docs_url="/api/docs", # Customize if needed
    # redoc_url="/api/redoc"  # Customize if needed
)

# --- Configure CORS Middleware ---
# This MUST come AFTER `app = FastAPI(...)` and ideally before routers are included.
origins = [
    "http://localhost:3000",  # Default React dev server port
    "http://127.0.0.1:3000",   # Also for React dev server
    # Add other origins if your frontend is served from a different port/domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allows cookies, authorization headers
    allow_methods=["*"],    # Allows all standard methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],    # Allows all headers
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
    
    # The PROJECT_ROOT_DIR for resolving paths like VECTOR_STORE_PATH
    # should be relative to where this script is or an absolute known path.
    # If settings.VECTOR_STORE_PATH is relative (e.g., "data/processed/vector_store"),
    # it needs a base. If PROJECT_ROOT_DIR_FOR_MODULES is 'backend', then:
    vector_store_full_path = os.path.join(PROJECT_ROOT_DIR_FOR_MODULES, settings.VECTOR_STORE_PATH)
    if os.path.exists(vector_store_full_path):
        logger.info(f"Vector Store Path ({settings.VECTOR_STORE_PATH}) found at: {vector_store_full_path}")
    else:
        logger.warning(f"Vector Store Path ({settings.VECTOR_STORE_PATH}) NOT found at: {vector_store_full_path}. Document Q&A may fail.")
        
    logger.info("--- FastAPI Application Startup Complete ---")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("--- FastAPI Application Shutdown Sequence Initiated ---")
    logger.info("--- FastAPI Application Shutdown Complete ---")


# --- Root Endpoint ---
@app.get("/", tags=["Health Check"])
async def read_root():
    """
    Root endpoint for the API.
    Provides a simple health check and welcome message.
    """
    return {
        "message": "Welcome to the Syngenta AI Agent API!",
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "docs_url": app.docs_url, # FastAPI automatically sets these
        "redoc_url": app.redoc_url # FastAPI automatically sets these
    }

# --- Main block for direct execution (less common for FastAPI) ---
if __name__ == "__main__":
    logger.warning("This FastAPI app (app/main.py) is being run directly. "
                   "It's recommended to use Uvicorn via the project's root main.py (Typer CLI) "
                   "or a direct Uvicorn command for production/development.")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)