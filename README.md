# AskMyDoc

**Chat with your PDFs through an authenticated, evidence-aware RAG workspace.**

AskMyDoc is a full-stack document Q&A app where users can upload PDFs, open a document-specific workspace, and ask grounded questions against retrieved evidence. What started as a local prototype is now a contract-driven v3 application with authenticated backend access, document lifecycle handling, persistent conversations, structured answer decisions, and integration coverage across the stack.

<img width="1835" height="943" alt="AskMyDoc workspace" src="https://github.com/user-attachments/assets/a2b5de3f-2083-42a2-a484-71eaae53e659" />

<img width="1835" height="943" alt="AskMyDoc chat view" src="https://github.com/user-attachments/assets/85b45629-167f-4340-bfda-b348ad0145b3" />

---

## Why I Built This

I wanted to understand what it takes to move a RAG app beyond a tutorial demo. That meant wiring together the full path: extraction, chunking, embeddings, retrieval, grounded generation, auth, persistence, storage cleanup, and frontend state management. The goal was never just "make chat answer a PDF", it was to make the surrounding product behavior reliable enough that real users could upload, return later, and trust the app's boundaries.

## Design Inspiration

The product experience is heavily inspired by Claude. The sidebar-first layout, home greeting, search modal, suggestion prompts, and overall pacing of the UI were all shaped by studying what makes modern AI interfaces feel calm and usable, then adapting those patterns to a document workspace rather than a general chat tool.

---

## What's New In V3

The README used to reflect the v2 app. The merged v3 work on `main` added a much stronger application contract and reliability layer:

- Contract-first API integration between FastAPI and Next.js, with the frontend consuming generated TypeScript types from the backend OpenAPI schema.
- Server-derived user identity between frontend and backend, so protected backend routes no longer trust caller-supplied user IDs.
- Explicit upload lifecycle handling with typed failure stages, reason codes, and cleanup reporting.
- Explicit delete lifecycle handling with partial-cleanup semantics and retry-friendly UI behavior.
- Structured chat answer decisions that return `intent`, `retrieval_mode`, `answer_status`, and `citations` alongside the answer text.
- Evidence-aware answer validation so the backend can fall back to an insufficient-context response when retrieved support is weak or the generated answer is not grounded enough.
- Answer-policy telemetry logging for retrieval quality, citation completeness, fallback reasons, and grounding outcomes.
- A centralized frontend workspace state module that routes upload, select, send, search, and delete flows through one state machine-like controller.
- Expanded backend integration tests plus frontend workspace transition tests covering success, failure, recovery, and stale async cancellation.

---

## Core Features

### Authenticated Workspace

- Email/password signup and login
- Google OAuth sign-in
- Protected app routes with authenticated backend proxying
- Signed internal headers from the frontend to the backend for server-trusted user identity

### Document Lifecycle

- PDF-only uploads
- Text extraction with `pdfplumber`
- Chunking and embedding into a per-document Chroma collection
- Document metadata persisted in Supabase
- Stored PDF uploaded to Supabase Storage
- Explicit upload failure categories for validation, indexing, storage, and metadata stages
- Explicit delete cleanup across storage, metadata, conversations, and vector index artifacts

### Grounded Chat

- Question answering scoped to the selected document
- Intent-aware retrieval policy that uses head retrieval for summary-style prompts and semantic retrieval with a quality gate for question-answer prompts
- Structured answer generation through a JSON harness
- Evidence-aware validation before returning an answer
- Insufficient-context fallback when retrieval or grounding is not strong enough
- Citation-bearing chat responses at the API layer

### Persistent Conversations

- Conversations are created per user and per document
- User and assistant messages are stored in Supabase
- Reopening a document restores its prior conversation history
- Conversation ownership is enforced server-side

### Frontend Reliability

- Centralized workspace orchestration for upload, select, send, search, and delete
- Recovery messaging when upload bootstrap finishes indexing but follow-up workspace setup fails
- Protection against stale async updates during rapid document switching or cancelled flows
- Delete flows that keep the UI aligned with partial-cleanup outcomes

---

## How It Works

```text
1. The user signs in to the Next.js app
2. Frontend API routes proxy requests to FastAPI using signed internal auth headers
3. A PDF upload is validated, text is extracted, and content is chunked
4. Chunks are embedded and stored in a Chroma collection keyed by document ID
5. The original PDF is uploaded to Supabase Storage and document metadata is persisted
6. The workspace creates or restores a document-scoped conversation
7. When the user sends a prompt, the backend selects a retrieval policy:
   - summary intent -> head retrieval
   - QA intent -> semantic retrieval with a quality gate
8. Retrieved excerpts are passed into the LLM with a structured output contract
9. The answer is checked for grounding against the cited evidence
10. The API returns a structured decision containing:
    answer, answer_status, intent, retrieval_mode, and citations
11. User and assistant messages are persisted for later reload
```

---

## Architecture Snapshot

### Backend

- `FastAPI` for the HTTP API
- `pdfplumber` for PDF extraction
- `LangChain` helpers for chunking and model integration
- `ChromaDB` for per-document vector storage
- `OpenAI` embeddings with `text-embedding-3-large`
- Configurable OpenAI chat model, defaulting to `gpt-5.4-nano`
- `Supabase` for relational persistence and PDF storage
- Persistence repositories that isolate document, conversation, message, and storage concerns
- Authz services that enforce resource ownership before protected operations run

### Frontend

- `Next.js 14` App Router with `TypeScript`
- `NextAuth.js` for credentials and Google sign-in
- Route handlers that proxy browser calls to the backend
- Shared generated API contract in `frontend/lib/api-contract.ts`
- A workspace state module that coordinates document and chat transitions
- Tailwind-based UI modeled after modern assistant products

---

## Reliability And Testing

V3 put much more emphasis on behavior guarantees, not just happy-path demos.

- Backend coverage includes authorization, bootstrap defaults, vector store behavior, RAG policy behavior, lifecycle flows, API contract sync, and app-level integration tests.
- Frontend coverage includes workspace transition tests for upload, selection, send, delete, recovery behavior, and stale async cancellation.
- The repo also includes a manual regression guide in [TESTING.md](/home/biloo0/Projects/AI chatbot/TESTING.md) covering end-to-end user and security flows.

Representative test areas:

- ownership enforcement across documents and conversations
- upload lifecycle failure handling and cleanup semantics
- delete lifecycle partial-failure behavior
- generated frontend contract staying in sync with backend OpenAPI
- evidence-aware chat fallback behavior
- answer policy telemetry emission

---

## Technical Decisions

**Why RAG instead of fine-tuning?**

The app needs answers anchored to user-supplied PDFs, not frozen knowledge baked into model weights. Retrieval keeps the knowledge base replaceable per document and per user.

**Why ChromaDB?**

For this project, per-document local vector persistence is enough to prove retrieval architecture without introducing a separate managed vector service too early.

**Why a generated frontend contract?**

Once lifecycle states and structured chat responses became richer, hand-maintaining request/response shapes across frontend and backend became a reliability risk. Generating the TypeScript contract from the backend schema keeps both sides aligned.

**Why server-derived identity?**

The backend should authorize based on identity asserted by trusted server infrastructure, not on a user ID supplied by the browser. The Next.js proxy signs internal headers and the backend verifies them before serving protected routes.

**Why answer-policy gating?**

A RAG app is only as trustworthy as its refusal behavior. V3 adds retrieval quality checks, structured output validation, and grounding validation so the system can explicitly say "I don't have enough support" instead of bluffing.

---

## Data Handling

- Uploaded PDFs are processed in memory, then stored in Supabase Storage.
- Vector embeddings are stored in Chroma collections namespaced by document ID.
- Conversations and messages are stored in Supabase and scoped by ownership.
- Deleting a document is intended to remove its visible metadata, stored PDF, related conversations/messages, and retrieval index artifacts.
- Chat responses can carry citations and answer-status metadata even when the UI is currently focused on the conversational rendering.

---

## Version History

| Version | Description |
|---------|-------------|
| V1 | Local-first single-document RAG prototype. No auth, no persistence, no multi-user boundaries. |
| V2 | Auth, persistent documents, conversation history, improved workspace UI, and multi-user support. |
| V3 | Contract-driven lifecycle handling, backend-enforced ownership, frontend proxy auth, evidence-aware chat answers, telemetry, and stronger integration coverage. |

---

## Future Directions

- Surface citations directly in the chat UI
- Add OCR fallback for scanned PDFs
- Support multi-document retrieval in one workspace
- Add streaming responses
- Move from local vector persistence to a more scalable deployment strategy when needed
