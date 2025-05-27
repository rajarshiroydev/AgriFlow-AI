# Pydantic models for API requests/responses
# SYNGENTA_AI_AGENT/app/models.py

from pydantic import BaseModel, Field
from typing import Optional, List, Any

class ChatQueryRequest(BaseModel):
    """
    Request model for the /chat endpoint.
    """
    query: str = Field(..., description="The natural language query from the user.")
    user_id: Optional[str] = Field(None, description="Optional user ID for tracking or personalization.")
    # session_id: Optional[str] = Field(None, description="Optional session ID for conversation history.") # Future use

class ChatQueryResponse(BaseModel):
    """
    Response model for the /chat endpoint.
    Mirrors the structure returned by agents.hybrid_orchestrator_agent.run_hybrid_query
    """
    answer: str = Field(..., description="The final synthesized answer to the user's query.")
    
    # Debugging and transparency fields
    query_type_debug: Optional[str] = Field(None, description="The type of query determined by the orchestrator (DOCUMENT_ONLY, DATABASE_ONLY, HYBRID, UNKNOWN).")
    decomposed_doc_question_debug: Optional[str] = Field(None, description="The sub-question formulated for document retrieval (if any).")
    decomposed_db_question_debug: Optional[str] = Field(None, description="The sub-question formulated for database querying (if any).")
    generated_sql: Optional[str] = Field(None, description="The SQL query generated for database interaction (if any).")
    
    sources: List[str] = Field(default_factory=list, description="List of source document names or identifiers used for RAG.")
    
    debug_info_orchestrator: Optional[str] = Field(None, description="Additional debug information from the orchestration process.")
    error: Optional[str] = Field(None, description="Error message if the query processing failed at some stage.")

    # Example of how you might add more structured context in the future
    # document_context_snippets: Optional[List[Dict[str, Any]]] = Field(None, description="Snippets of context from documents.")
    # database_results_summary: Optional[Any] = Field(None, description="Summary of raw database results.")

    class Config:
        # This allows Pydantic to handle cases where a default value is None but you want to explicitly show it in the schema
        # orjson_mode = True # if using orjson for faster JSON, not strictly needed here
        pass