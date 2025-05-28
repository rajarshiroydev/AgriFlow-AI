import logging
from fastapi import APIRouter, HTTPException, Body
from typing import Annotated

from agents.hybrid_orchestrator_agent import run_hybrid_query
from app.models import ChatQueryRequest, ChatQueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1",
    tags=["Chat Agent"]
)

@router.post("/chat", response_model=ChatQueryResponse)
async def handle_chat_query(
    request: Annotated[ChatQueryRequest, Body(
        description="User query to be processed by the AI agent, optionally with conversation history.",
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
            },
            {
                "summary": "Query with History",
                "value": {
                    "query": "What about for international destinations?",
                    "user_id": "user123",
                    "history": [
                        {"sender": "user", "text": "What is our policy on shipping high-value goods?"},
                        {"sender": "ai", "text": "Our policy states X, Y, and Z for high-value goods."}
                    ]
                }
            }
        ]
    )]
):
    logger.info(f"Received chat query: '{request.query}' (User ID: {request.user_id or 'N/A'}) (History turns: {len(request.history) if request.history else 0})")
    
    try:
        result_dict = run_hybrid_query(
            user_query=request.query,
            history=request.history
        )
        response = ChatQueryResponse(**result_dict)
        logger.info(f"Successfully processed query. Answer snippet: {response.answer[:100]}...")
        return response
    except ImportError as ie:
        logger.critical(f"ImportError during chat query handling: {ie}. Check PYTHONPATH and module locations.", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server configuration error: {str(ie)}")
    except Exception as e:
        logger.error(f"Unexpected error processing chat query '{request.query}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")