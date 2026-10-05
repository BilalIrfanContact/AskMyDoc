"""Re-embed already-indexed documents with chunk labels, keeping their document and chunk IDs.

Documents indexed before chunk labelling (see `backend/services/chunk_labels.py`) still search on the
bare chunk text. This reads each collection's stored chunks, labels and embeds them, and only then
replaces the collection, so chunk IDs, the app's library and eval gold mappings stay valid. Documents
whose chunks already carry labels are skipped unless `--force` is given.

    .venv/bin/python -m backend.scripts.reindex_documents --all
    .venv/bin/python -m backend.scripts.reindex_documents DOCUMENT_ID [DOCUMENT_ID ...]
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


def reindex_document(document_id: str, force: bool = False) -> str:
    """Relabel one document in place and return what happened: "reindexed" or "skipped"."""
    restore_interrupted_swap(document_id)
    stored = get_persisted_collection(document_id).get(include=["documents", "metadatas"])
    rows = sorted(
        zip(stored["ids"], stored["documents"], stored["metadatas"]),
        key=lambda row: int(row[0].rsplit(":", 1)[1]),
    )
    if not force and rows and all((metadata or {}).get("label") for _, _, metadata in rows):
        return "skipped"
    expected_ids = [f"{document_id}:chunk:{index}" for index in range(len(rows))]
    if [chunk_id for chunk_id, _, _ in rows] != expected_ids:
        raise ValueError("chunk IDs are not a contiguous <document_id>:chunk:<index> sequence")

    payload = prepare_index_payload(document_id, [document for _, document, _ in rows])
    replace_index_payload(document_id, payload)
    return "reindexed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-embed indexed documents with chunk labels.")
    parser.add_argument("document_ids", nargs="*", help="Documents to re-index.")
    parser.add_argument("--all", action="store_true", help="Re-index every document in the local store.")
    parser.add_argument("--force", action="store_true", help="Re-index documents that already have labels.")
    args = parser.parse_args(argv)
    if bool(args.all) == bool(args.document_ids):
        parser.error("pass document IDs or --all, not both")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    failures = 0
    for document_id in list_document_ids() if args.all else args.document_ids:
        try:
            outcome = reindex_document(document_id, force=args.force)
        except Exception as exc:
            failures += 1
            outcome = f"FAILED: {exc}"
        print(f"{document_id} {outcome}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
