from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .bootstrap import initialize_backend_environment

initialize_backend_environment()

from .routers import chat, conversations, documents, upload

app = FastAPI(title="AskMyDoc")

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
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "message": "AskMyDoc API. Use /health, /upload, /chat, /conversations, and /documents endpoints."
    }
