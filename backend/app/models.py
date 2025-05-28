# SYNGENTA_AI_AGENT/app/models.py

from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict # Added Dict

class HistoryMessage(BaseModel):
    """
    Represents a single message turn in the conversation history.
    'sender' can be 'user' or 'ai'.
    'text' is the content of the message.
    """
    sender: str = Field(..., description="Sender of the message, e.g., 'user' or 'ai'")
    text: str = Field(..., description="The text content of the message.")

class ChatQueryRequest(BaseModel):
    """
    Request model for the /chat endpoint.
    Now includes conversation history.
    """
    query: str = Field(..., description="The natural language query from the user.")
    user_id: Optional[str] = Field(None, description="Optional user ID for tracking or personalization.")
    # session_id: Optional[str] = Field(None, description="Optional session ID for conversation history.") # Still future use if we switch to server-side
    history: Optional[List[HistoryMessage]] = Field(None, description="A list of previous user queries and AI responses for conversational context.")

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

    class Config:
        pass