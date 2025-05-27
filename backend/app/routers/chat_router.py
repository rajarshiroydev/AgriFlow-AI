import logging
from fastapi import APIRouter, HTTPException, Body
from typing import Annotated # For newer FastAPI Body usage

# Assuming your project root is correctly in PYTHONPATH
# or Uvicorn is run from the project root.
from agents.hybrid_orchestrator_agent import run_hybrid_query
from app.models import ChatQueryRequest, ChatQueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1",  # Optional: prefix for all routes in this router
    tags=["Chat Agent"] # Tags for OpenAPI documentation
)

@router.post("/chat", response_model=ChatQueryResponse)
async def handle_chat_query(
    request: Annotated[ChatQueryRequest, Body(
        description="User query to be processed by the AI agent.",
        examples=[
            {
                "summary": "Simple Database Query",
                "value": {"query": "What is the total sales amount for all orders?"}
            },
            {
                "summary": "Simple Document Query",
                "value": {"query": "What is our company's policy on data privacy?"}
            },
            {
                "summary": "Hybrid Query",
                "value": {"query": "According to our inventory write-off policy, what was the total value of written-off inventory last year for product ID 'XYZ123'?"}
            },
            {
                "summary": "Query with User ID",
                "value": {"query": "List my recent orders.", "user_id": "user123"}
            }
        ]
    )]
):
    """
    Receives a user query, processes it using the hybrid orchestration logic,
    and returns a comprehensive answer.
    """
    logger.info(f"Received chat query: '{request.query}' (User ID: {request.user_id or 'N/A'})")
    
    try:
        # Call the core hybrid query orchestrator function
        # Note: request.user_id is not currently used by run_hybrid_query but is passed for future use.
        # If run_hybrid_query needs user_id, you'll modify its signature and logic.
        result_dict = run_hybrid_query(user_query=request.query)

        # Map the dictionary result to the Pydantic response model
        # Pydantic will validate the structure.
        response = ChatQueryResponse(**result_dict)
        
        logger.info(f"Successfully processed query. Answer snippet: {response.answer[:100]}...")
        return response

    except ImportError as ie:
        # This might happen if agent modules are not found due to PYTHONPATH issues
        logger.critical(f"ImportError during chat query handling: {ie}. Check PYTHONPATH and module locations.", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Server configuration error: Could not import necessary agent modules. {str(ie)}"
        )
    except Exception as e:
        # Catch-all for unexpected errors within the endpoint logic
        # or if run_hybrid_query raises an unhandled exception (though it seems to handle its own errors well)
        logger.error(f"Unexpected error processing chat query '{request.query}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )