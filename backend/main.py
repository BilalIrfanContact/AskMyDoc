import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Disable Chroma telemetry early to avoid noisy capture() errors.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY", "false")
os.environ.setdefault("CHROMA_ENABLE_TELEMETRY", "false")
os.environ.setdefault("POSTHOG_DISABLED", "1")

from .routers import upload, chat

load_dotenv()

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


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "AskMyDoc API. Use /health, /upload, /chat endpoints."}
