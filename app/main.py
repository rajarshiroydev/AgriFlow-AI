# FastAPI app instantiation, global handlers

from fastapi import FastAPI
import logging

# Assuming your routers are in app.routers.chat_router etc.
from app.routers import chat_router # Or your specific router for the chat endpoint

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Syngenta AI Agent API",
    description="API for the Syngenta AI Agent Hackathon.",
    version="0.1.0"
)

# Include your routers
app.include_router(chat_router.router) # Example
# app.include_router(utils_router.router) # If you have one

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI Application startup complete.")
    # You can add initial setup here if needed, e.g., initializing ML models
    # but keep it light for fast startups.

@app.get("/")
async def read_root():
    return {"message": "Syngenta AI Agent API is running!"}


# That's handled by your root main.py (Typer) or directly by the docker-compose command.