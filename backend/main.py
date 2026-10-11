from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .bootstrap import initialize_backend_environment

initialize_backend_environment()

from .routers import chat, conversations, documents, upload
from .services.persistence.common import PersistenceError
from .services.persistence.documents_repository import ping_database

from .services.request_body_limit import RequestBodyLimitMiddleware

app = FastAPI(title="AskMyDoc")
app.add_middleware(RequestBodyLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(documents.router)


@app.get("/health")
async def health_check():
    """Uptime monitors ping this; the database read keeps the free Supabase project from pausing."""
    try:
        await run_in_threadpool(ping_database)
    except PersistenceError:
        return JSONResponse(status_code=503, content={"status": "database_unavailable"})
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "message": "AskMyDoc API. Use /health, /upload, /chat, /conversations, and /documents endpoints."
    }
