# Context-PDF
PDF chat assistant powered by retrieval‑augmented generation

## Features
- Upload a PDF and index it locally with ChromaDB
- Ask natural-language questions in a chat UI
- Answers are constrained to the document content

## Structure
- `backend/` FastAPI + LangChain + ChromaDB
- `frontend/` Next.js (App Router) + Tailwind

## Quick Start

### Backend
1. Create a virtualenv and install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```
2. Add your key:
   ```bash
   cp backend/.env.example backend/.env
   ```
3. Run the API:
   ```bash
   uvicorn backend.main:app --reload
   ```

### Frontend
1. Install deps:
   ```bash
   cd frontend
   npm install
   ```
2. Start the dev server:
   ```bash
   npm run dev
   ```

## Environment
Frontend expects the backend at `http://localhost:8000`. To change it, set:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## API
- `POST /upload` → upload and index a PDF
- `POST /chat` → ask a question for a given `document_id`
- `GET /health` → health check

## Notes
- Uploading a PDF returns a `document_id` that is used for subsequent questions.
- The assistant only answers from retrieved chunks.
- Scanned/image-only PDFs require OCR (not included).

## Security
- Never commit `backend/.env`.
