from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import DocumentsResponse
from ..services.supabase_store import SupabasePersistenceError, list_user_documents

router = APIRouter()


@router.get("/documents", response_model=DocumentsResponse)
async def get_user_documents(user_id: str = Query(..., description="Supabase user UUID")):
    try:
        documents = list_user_documents(user_id=user_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DocumentsResponse(documents=documents)
