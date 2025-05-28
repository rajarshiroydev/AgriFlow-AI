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
        description="User query to be processed by the AI agent, optionally with conversation history and user_id.",
        examples=[
            {
                "summary": "Simple Database Query (as guest)",
                "value": {"query": "What is the total sales amount for all orders?", "user_id": "guest_global"}
            },
            {
                "summary": "Financial Query (as manager)",
                "value": {"query": "What is the profit margin for product X?", "user_id": "manager_emea"}
            },
            {
                "summary": "Financial Query (as analyst - should be denied)",
                "value": {"query": "What is the profit margin for product X?", "user_id": "analyst_us"}
            },
            {
                "summary": "US Sales Query (as US analyst)",
                "value": {"query": "Total sales in US?", "user_id": "analyst_us"}
            },
             {
                "summary": "EMEA Sales Query (as US analyst - should be filtered or denied by SQL if region column check is effective)",
                "value": {"query": "Total sales in EMEA?", "user_id": "analyst_us"}
            }
        ]
    )]
):
    logger.info(f"Received chat query: '{request.query}' (User ID: {request.user_id or 'N/A'}) (History turns: {len(request.history) if request.history else 0})")
    
    try:
        result_dict = run_hybrid_query(
            user_query=request.query,
            history=request.history,
            user_id=request.user_id # Pass user_id to orchestrator
        )
        response = ChatQueryResponse(**result_dict)
        # Avoid logging full answer if it's sensitive and access was just granted by check_query_access
        # The audit log in access_control.py already logs the attempt.
        logger.info(f"Successfully processed query for user '{request.user_id or 'N/A'}'. Query type: {response.query_type_debug}")
        return response
    except ImportError as ie:
        logger.critical(f"ImportError: {ie}. Check PYTHONPATH.", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server config error: {str(ie)}")
    except Exception as e:
        logger.error(f"Unexpected error processing chat query '{request.query}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")