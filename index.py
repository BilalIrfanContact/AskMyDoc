"""Vercel's entrypoint for the backend: Vercel serves the FastAPI `app` it finds in this file.

Locally, run the same app with `uvicorn backend.main:app --reload`.
"""

from backend.main import app

__all__ = ["app"]
