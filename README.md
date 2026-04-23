# AskMyDoc

**Chat with your PDFs. Pick up where you left off.**

AskMyDoc is a full-stack RAG application that lets authenticated users upload PDF documents and have grounded, document-accurate conversations with them. Built across two versions  from a local single-document prototype to a multi-user authenticated application with persistent documents and conversation history.

![AskMyDoc Screenshot](img/askmydoc-screenshot.png)

---

## Why I Built This

Built to understand how a practical RAG system works across the full path extraction, chunking, embeddings, vector search, prompt construction, and grounded generation. The goal was to go beyond a tutorial-level project and wire together a production-adjacent architecture: real auth, real persistence, real deployment. V1 proved the pipeline. V2 turned it into something people can actually sign up for and use.

## Design Inspiration

The UI/UX is heavily inspired by Claude (Anthropic). The color scheme,
typography, sidebar layout, personalized greeting on the home screen,
suggestion pills, search modal, and overall interaction patterns are
all modeled after Claude's interface. The goal was to study and
replicate what makes a well-designed AI application feel natural and
polished and apply those same principles to a document-focused use
case.

---

## Features

### Authentication
- Email and password signup and login
- Google OAuth sign-in
- Route protection via middleware. Unauthenticated users cannot access the app

### Document Management
- PDF documents are indexed and persisted per user
- Uploaded documents history visible in a sidebar
- Hover-to-delete control with confirmation modal for removing documents
- Searchable document modal with live filtering as you type
- Deleting a document also removes its stored PDF, vector index, and related chat history
- Documents survive sessions, reload the page, your documents are still there

### RAG Pipeline
- PDF text extraction with `pdfplumber`
- Overlapping text chunking with `RecursiveCharacterTextSplitter`
- Embeddings with OpenAI `text-embedding-3-large`
- Vector storage and retrieval with ChromaDB
- Grounded answer generation ensures responses are strictly based on document content, not model knowledge

### Conversation Persistence
- Every conversation is saved to the database per user per document
- Reopen any previous document and the full conversation history loads back

### UX
- Personalized greeting on the home screen using the authenticated user's name
- Home screen greeting includes the app icon and responsive typography
- Sidebar with recent document navigation
- Skeleton loading state during conversation retrieval
- Typing-style loader while the assistant searches the document and prepares a response
- Auto-scroll to the latest message when the user sends a message or the assistant replies
- Suggestion pills on the home screen to guide first questions
- Clean upload → indexing → chat flow

---

## How It Works

```
1. User signs up or logs in (email/password or Google OAuth)
         ↓
2. User uploads a PDF → FastAPI extracts text with pdfplumber
         ↓
3. Text is chunked with overlapping segments
         ↓
4. Chunks are embedded with text-embedding-3-large
         ↓
5. Embeddings are stored in ChromaDB under a UUID document_id
   PDF metadata is stored in Supabase (documents table)
         ↓
6. User asks a question → question is embedded
         ↓
7. ChromaDB retrieves the top-k most similar chunks
         ↓
8. Retrieved context + question are sent to the LLM
   The model is instructed to answer strictly from provided context
         ↓
9. Answer is returned to the frontend and rendered in the chat view
   The UI shows a typing-style loader during retrieval/generation and auto-scrolls to the newest message
   Message is persisted to Supabase (messages table)
         ↓
10. User can close the tab, return later, and the conversation is still there
```

---

## Tech Stack

### Backend
- **FastAPI:** REST API server
- **pdfplumber:** PDF text extraction
- **LangChain:** Text chunking and RAG pipeline orchestration
- **ChromaDB:** Local vector store for embeddings
- **OpenAI API:** `text-embedding-3-large` for embeddings, `gpt-5.4-nano` for generation
- **Supabase:** PostgreSQL for user, document, conversation, and message persistence + file storage
- **Pydantic:** Request and response validation

### Frontend
- **Next.js 14** (App Router) with **TypeScript**
- **NextAuth.js**  authentication with Google OAuth and credentials provider
- **Tailwind CSS**  styling
- **Supabase JS** client-side database access

---

## Project Structure

```
askmydoc/
│
├── backend/
│   ├── main.py                    # FastAPI app, CORS, router registration
│   ├── routers/
│   │   ├── upload.py              # POST /upload
│   │   ├── chat.py                # POST /chat
│   │   ├── conversations.py       # Conversation CRUD endpoints
│   │   └── documents.py           # Document listing and deletion endpoints
│   ├── services/
│   │   ├── pdf_extractor.py       # pdfplumber text extraction
│   │   ├── text_chunker.py        # RecursiveCharacterTextSplitter
│   │   ├── embedder.py            # OpenAI embedding model loader
│   │   ├── vector_store.py        # ChromaDB persistence and retrieval
│   │   ├── rag_pipeline.py        # Retrieval + grounded answer generation
│   │   └── supabase_store.py      # Supabase persistence helpers
│   ├── models/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── .env.example
│   └── requirements.txt
│
|── frontend/
   ├── app/
   │   ├── layout.tsx             # App shell
   │   ├── page.tsx               # Authenticated home/workspace
   │   ├── login/page.tsx         # Login route
   │   ├── signup/page.tsx        # Signup route
   │   └── api/
   │       ├── auth/[...nextauth]/route.ts
   │       └── auth/signup/route.ts
   ├── components/
   │   ├── HomeClient.tsx         # Main app shell, sidebar, modal logic
   │   ├── PDFUploader.tsx        # Upload UI
   │   ├── ChatWindow.tsx         # Conversation display
   │   ├── ChatInput.tsx          # Auto-growing message input
   │   ├── MessageBubble.tsx      # Individual message UI
   │   ├── LoginForm.tsx          # Login form
   │   └── SignupForm.tsx         # Signup form
   ├── lib/
   │   ├── api.ts                 # Frontend API client
   │   ├── auth-users.ts          # Supabase user CRUD helpers
   │   ├── password.ts            # Password hash and verify
   │   └── supabase-admin.ts      # Supabase admin client
   ├── middleware.ts              # Route protection
   └── auth.ts                   # NextAuth configuration


```

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/BilalIrfanContact/AskMyDoc.git
cd askmydoc
```

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate        
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# Fill in your environment variables
uvicorn backend.main:app --reload
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# Fill in your environment variables
npm run dev
```

Visit `http://localhost:3000`

---

## Environment Variables

### Backend (`backend/.env`)

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_CHAT_MODEL=gpt-5.4-nano
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_STORAGE_BUCKET=your_bucket_name
ANONYMIZED_TELEMETRY=false
CHROMA_TELEMETRY=false
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your_nextauth_secret
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

---

## API setup

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload a PDF. Returns `document_id`, `chunk_count`, `stored_count`. Persists metadata to Supabase if `user_id` is provided. |
| `POST` | `/chat` | Send a question with `document_id`. Returns a grounded answer. Persists messages if `user_id` and `conversation_id` are provided. |
| `POST` | `/conversations` | Create a conversation for a `user_id` and `document_id`. |
| `GET` | `/conversations` | List conversations for a user, optionally filtered by `document_id`. |
| `GET` | `/conversations/{id}/messages` | Return full message history for a conversation. |
| `GET` | `/documents` | Return all documents uploaded by a user. |
| `DELETE` | `/documents/{id}` | Delete a user document and clean up its Supabase metadata, stored PDF, related conversations/messages, and Chroma collection. |
| `GET` | `/health` | Basic health check. |

---

## Database Schema

The application expects the following tables in Supabase:

```sql
-- Users (see docs/supabase-users.sql)
users: id, email, name, password_hash, created_at

-- Documents
documents: id, user_id, filename, storage_url, uploaded_at

-- Conversations
conversations: id, user_id, document_id, created_at

-- Messages
messages: id, conversation_id, role, content, created_at
```

---

## Technical Decisions

**Why RAG over fine-tuning?**
Fine-tuning bakes knowledge into model weights  it can't be updated without retraining. RAG retrieves from the actual document at query time, making it accurate, updatable, and cost-effective for document-specific Q&A.

**Why ChromaDB over Pinecone or Weaviate?**
For a portfolio project with controlled usage, a locally persisted ChromaDB instance deployed alongside the backend on Railway is sufficient, free, and requires zero external infrastructure. Pinecone would be the right call for multi-instance horizontal scaling.

**Why `text-embedding-3-large` over `text-embedding-3-small`?**
Higher dimensional embeddings produce better semantic similarity scores for document retrieval, which directly improves answer quality. The cost difference at portfolio-scale usage is negligible.

**Why chunk size 2000 with 200 overlap?**
Larger chunks preserve more context per retrieval, reducing answer fragmentation for long-form documents. The 200-character overlap ensures relevant content at chunk boundaries is not lost.

**Why Supabase over a self-managed PostgreSQL instance?**
Supabase provides PostgreSQL, file storage, and a client SDK in one place. For a portfolio project it eliminates significant infrastructure overhead while still demonstrating real database design skills.

**Why NextAuth.js?**
It handles Google OAuth and credentials providers cleanly with built-in session management and middleware-based route protection. No need to implement token flows manually.

---

## Data Handling

- Uploaded PDFs are processed in memory and stored in Supabase Storage they are not written to the local filesystem
- Embeddings are persisted in a local ChromaDB directory on the backend server
- Conversation messages are stored in Supabase and scoped strictly per user
- No PDF content or embeddings are shared across users each document collection is namespaced by a UUID

---

## Future Improvements

- Streaming responses in the chat UI
- Source citations surface the specific chunk and page number behind each answer
- OCR fallback for scanned or image-based PDFs
- Multi-document workspace ask questions across multiple PDFs simultaneously
- Cloud vector database for horizontal scaling

---

## Version History

| Version | Description |
|---------|-------------|
| V1 | Local-first single-document RAG. No auth, no persistence, no multi-user support. Proved the pipeline. |
| V2 | Full authentication (email + Google OAuth), Supabase persistence, conversation history, collapsible sidebar, search modal, upgraded UI. Current version. |
