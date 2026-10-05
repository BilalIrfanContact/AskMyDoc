"""Re-embed already-stored documents in place with the current embedding model, keeping their IDs.

Reads each collection's stored chunks and replaces the collection only once the new vectors are ready, so
chunk IDs, the app's library and eval gold mappings stay valid. Existing chunk metadata (such as labels from
the earlier labelling experiment) is kept. No chat model calls are made, only embeddings. Use it after changing
embedding models.

    .venv/bin/python -m backend.scripts.reindex_documents DOCUMENT_ID [DOCUMENT_ID ...]
    .venv/bin/python -m backend.scripts.reindex_documents --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.services.vector_store import (
    get_persisted_collection,
    list_document_ids,
    prepare_index_payload,
    replace_index_payload,
    restore_interrupted_swap,
)


def reindex_document(document_id: str) -> str:
    """Re-embed one document in place and return "reembedded"."""
    restore_interrupted_swap(document_id)
    stored = get_persisted_collection(document_id).get(include=["documents", "metadatas"])
    rows = sorted(
        zip(stored["ids"], stored["documents"], stored["metadatas"]),
        key=lambda row: int(row[0].rsplit(":", 1)[1]),
    )
    expected_ids = [f"{document_id}:chunk:{index}" for index in range(len(rows))]
    if [chunk_id for chunk_id, _, _ in rows] != expected_ids:
        raise ValueError("chunk IDs are not a contiguous <document_id>:chunk:<index> sequence")

    chunks = [document for _, document, _ in rows]
    payload = prepare_index_payload(document_id, chunks, [metadata or {} for _, _, metadata in rows])
    replace_index_payload(document_id, payload)
    return "reembedded"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-embed stored documents in place with the current embedding model.")
    parser.add_argument("document_ids", nargs="*", help="Documents to re-embed.")
    parser.add_argument("--all", action="store_true", help="Re-embed every document in the local store.")
    args = parser.parse_args(argv)
    if bool(args.all) == bool(args.document_ids):
        parser.error("pass document IDs or --all, not both")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    failures = 0
    for document_id in list_document_ids() if args.all else args.document_ids:
        try:
            outcome = reindex_document(document_id)
        except Exception as exc:
            failures += 1
            outcome = f"FAILED: {exc}"
        print(f"{document_id} {outcome}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
