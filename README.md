![AskMyDoc Screenshot](img/askmydoc-screenshot.png)

# AskMyDoc
PDF chat assistant powered by retrieval‑augmented generation

Upload a PDF and ask questions grounded in its content. This project uses a retrieval‑augmented generation (RAG) pipeline: text is extracted from the PDF, chunked, embedded with OpenAI, stored locally in ChromaDB, and retrieved at question time to keep answers aligned with the document.

## Why I built this
Built to understand how RAG pipelines work end-to-end from text extraction and chunking strategy to vector similarity search and context-grounded generation. The goal was to move beyond tutorial-level AI projects and wire together a production-like architecture using real tools (LangChain, ChromaDB, OpenAI) rather than toy examples

## Features
- PDF upload with local indexing
- Conversational Q&A with document‑only answers
- Chunk count and stored count indicator after upload
- Local vector store, no external DB required

## Architecture Overview
1. **Upload**: PDF is sent to `/upload`.
2. **Extract**: `pdfplumber` extracts text.
3. **Chunk**: text is split into overlapping chunks.
4. **Embed**: chunks are embedded using `text-embedding-3-small`.
5. **Store**: embeddings are stored in ChromaDB under a unique `document_id`.
6. **Query**: questions are embedded and matched against stored chunks.
7. **Answer**: `gpt-4o-mini` answers using only retrieved context.

## Tech Stack
**Backend**
- FastAPI
- pdfplumber
- LangChain + langchain‑chroma
- ChromaDB (local persistence)
- OpenAI API (embeddings + chat completion)

**Frontend**
- Next.js (App Router)
- TypeScript
- Tailwind CSS

## Project Structure
- `backend/`
- `backend/routers/`
- `backend/services/`
- `backend/models/`
- `frontend/`
- `frontend/app/`
- `frontend/components/`

## Quick Start

### 1) Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn backend.main:app --reload
```

### 2) Frontend
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`.

## Environment Variables
**Backend**
```
OPENAI_API_KEY=your_openai_api_key_here
```

**Frontend**
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## API
`POST /upload`  
Accepts a PDF file (multipart form). Returns a `document_id` plus chunk counts.

`POST /chat`  
Body: `{ "document_id": "<uuid>", "question": "..." }`

`GET /health`  
Basic health check.

## Data Handling
- PDFs are processed in memory and not stored by default.
- Embeddings are persisted locally in `backend/chroma_db/`.
- Answers are generated strictly from retrieved chunks.


## OpenAI Usage
This project uses:
- `text-embedding-3-small` for embeddings
- `gpt-4o-mini` for chat responses

Make sure your API key has access and your billing is active.

## Roadmap
- OCR fallback for scanned PDFs
- Multi‑document workspace
- Source citations per answer
- Streaming responses in UI
