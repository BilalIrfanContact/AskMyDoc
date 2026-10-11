"""One-time copy of the benchmark filings' local Chroma indexes into the Supabase chunk store.

Keeping their document IDs keeps the benchmark's gold chunk IDs valid, and reusing the stored vectors means no
embedding calls. Only documents listed in the eval index file are copied, so app test uploads stay behind. Of
those, only ones embedded with the current model and input format are copied; older ones could not be searched
anyway and are listed as skipped (re-embed them later with `reindex_documents`). Documents Supabase already has
are skipped, so the copy can be rerun after a failure.

Reads `backend/chroma_db`, so it needs `chromadb==0.5.5`, which the app no longer installs.

    .venv/bin/python -m backend.scripts.copy_chroma_to_supabase          # report only
    .venv/bin/python -m backend.scripts.copy_chroma_to_supabase --apply  # copy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.services.ai_providers import embedding_model_name
from backend.services.vector_store import EMBEDDING_INPUT, IndexPayload, list_document_ids, write_index_payload


CHROMA_DIRECTORY = Path(__file__).resolve().parents[1] / "chroma_db"
EVAL_INDEX = Path(__file__).resolve().parents[2] / "evals/financial-filings/indexed-documents.local.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy the benchmark filings' Chroma indexes into Supabase.")
    parser.add_argument("--apply", action="store_true", help="Write to Supabase; without it, only report.")
    parser.add_argument("--indexed", type=Path, default=EVAL_INDEX, help="Eval index file listing the documents to copy.")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIRECTORY),
        settings=Settings(anonymized_telemetry=False, is_persistent=True, persist_directory=str(CHROMA_DIRECTORY)),
    )
    wanted = {entry["document_id"] for entry in json.loads(args.indexed.read_text())["documents"]}
    already_copied = set(list_document_ids())
    failures = 0
    for collection in sorted(client.list_collections(), key=lambda item: item.name):
        name = collection.name
        if name not in wanted:
            continue
        metadata = collection.metadata or {}
        model = metadata.get("embedding_model", "text-embedding-3-large")
        if model != embedding_model_name() or metadata.get("embedding_input") != EMBEDDING_INPUT:
            print(f"{name} skipped: embedded with {model}", file=sys.stderr)
            continue
        if name in already_copied:
            print(f"{name} skipped: already in Supabase", file=sys.stderr)
            continue
        if not args.apply:
            print(f"{name} would copy {collection.count()} chunks", file=sys.stderr)
            continue
        try:
            stored = collection.get(include=["documents", "metadatas", "embeddings"])
            rows = sorted(
                zip(stored["ids"], stored["documents"], stored["metadatas"], stored["embeddings"]),
                key=lambda row: (row[2] or {}).get("chunk_index", 0),
            )
            payload = IndexPayload(
                ids=[row[0] for row in rows],
                documents=[row[1] for row in rows],
                metadatas=[row[2] or {} for row in rows],
                embeddings=[[float(value) for value in row[3]] for row in rows],
            )
            print(f"{name} copied {write_index_payload(name, payload, embedding_model=model)} chunks", file=sys.stderr)
        except Exception as exc:
            failures += 1
            print(f"{name} FAILED: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
