from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    status: str
    document_id: str = Field(..., description="UUID for the uploaded document")
    chunk_count: int = Field(..., description="Number of chunks stored for retrieval")
    stored_count: int = Field(..., description="Number of chunks persisted in Chroma")


class ChatRequest(BaseModel):
    document_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str
