from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    status: Literal["success"]
    lifecycle_status: Literal["ready"] = Field(..., description="Lifecycle state for the upload flow")
    document_id: str = Field(..., description="UUID for the uploaded document")
    chunk_count: int = Field(..., description="Number of chunks stored for retrieval")
    stored_count: int = Field(..., description="Number of chunks persisted in Chroma")


class ChatRequest(BaseModel):
    document_id: str
    question: Optional[str] = None
    message: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str


class ConversationCreateRequest(BaseModel):
    document_id: str


class ConversationCreateResponse(BaseModel):
    conversation_id: str


class ConversationRecord(BaseModel):
    id: str
    user_id: str
    document_id: str
    created_at: Optional[str] = None


class ConversationsResponse(BaseModel):
    conversations: List[ConversationRecord]


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: Optional[str] = None


class ConversationMessagesResponse(BaseModel):
    messages: List[MessageRecord]


class DocumentRecord(BaseModel):
    id: str
    user_id: str
    filename: str
    storage_url: str
    uploaded_at: Optional[str] = None


class DocumentsResponse(BaseModel):
    documents: List[DocumentRecord]


class DeleteDocumentResponse(BaseModel):
    deleted: Literal[True]
    lifecycle_status: Literal["deleted"] = Field(..., description="Lifecycle state for the delete flow")
    cleanup_status: Literal["completed"] = Field(..., description="Cleanup outcome for the delete flow")
