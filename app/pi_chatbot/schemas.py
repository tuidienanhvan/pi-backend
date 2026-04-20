"""Pi Chatbot backend DTOs."""

from pydantic import BaseModel, Field


class ChatbotReplyRequest(BaseModel):
    site_url: str
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str = ""
    system_prompt: str = ""
    rag_context: str = ""          # injected by Rag plugin on client
    language: str = "auto"


class ChatbotReplyResponse(BaseModel):
    success: bool
    reply: str
    tokens_charged: int = 0
    provider_used: str = ""


class RagUploadResponse(BaseModel):
    success: bool
    doc_id: str
    chunks_indexed: int


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(3, ge=1, le=10)


class RagChunk(BaseModel):
    text: str
    score: float
    doc_id: str


class RagQueryResponse(BaseModel):
    success: bool
    chunks: list[RagChunk]
