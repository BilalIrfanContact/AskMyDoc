from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import AnswerCitation, ChatRequest, ChatResponse, ErrorDetailResponse
from ..services.conversation_turn import (
    ConversationTurnInput,
    ConversationTurnValidationError,
    execute_conversation_turn,
)
from ..services.internal_auth import require_authenticated_user
from ..services.persistence import PersistenceError

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorDetailResponse},
        401: {"model": ErrorDetailResponse},
        403: {"model": ErrorDetailResponse},
        404: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def chat(request: ChatRequest, user_id: str = Depends(require_authenticated_user)):
    try:
        decision = execute_conversation_turn(
            user_id=user_id,
            request=ConversationTurnInput(
                document_id=request.document_id,
                conversation_id=request.conversation_id,
                message=request.message,
                question=request.question,
            ),
        )
    except ConversationTurnValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        answer=decision.answer,
        intent=decision.intent,
        retrieval_mode=decision.retrieval_mode,
        answer_status=decision.answer_status,
        citations=[
            AnswerCitation(chunk_id=citation.chunk_id, excerpt=citation.excerpt)
            for citation in decision.citations
        ],
    )
