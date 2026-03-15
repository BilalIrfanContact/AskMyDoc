from fastapi import APIRouter, HTTPException

from ..models.schemas import ChatRequest, ChatResponse
from ..services.rag_pipeline import answer_question

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    answer = answer_question(document_id=request.document_id, question=question)
    return ChatResponse(answer=answer)
