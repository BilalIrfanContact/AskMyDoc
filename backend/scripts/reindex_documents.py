"""Re-index already-stored documents in place, keeping their document and chunk IDs.

Two jobs, both reading each collection's stored chunks and only replacing the collection once the new
vectors are ready, so chunk IDs, the app's library and eval gold mappings stay valid:

- Default: label documents indexed before chunk labelling (see `backend/services/chunk_labels.py`).
  Documents whose chunks already carry labels are skipped unless `--force` is given. Labelling makes
  one model call per chunk.
- `--reembed`: re-embed with the current embedding model, reusing the stored labels (and title). Use it
  after changing embedding models. Only a document without a stored title makes one model call, for
  the title. Documents without labels are skipped; label them first.

    .venv/bin/python -m backend.scripts.reindex_documents --all
    .venv/bin/python -m backend.scripts.reindex_documents --reembed DOCUMENT_ID [DOCUMENT_ID ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.services.chunk_labels import DocumentLabels, label_document, title_document
from backend.services.vector_store import (
    get_persisted_collection,
    list_document_ids,
    prepare_index_payload,
    replace_index_payload,
    restore_interrupted_swap,
)


def reindex_document(document_id: str, force: bool = False, reembed: bool = False) -> str:
    """Re-index one document in place and return what happened: "reindexed", "reembedded" or "skipped"."""
    restore_interrupted_swap(document_id)
    stored = get_persisted_collection(document_id).get(include=["documents", "metadatas"])
    rows = sorted(
        zip(stored["ids"], stored["documents"], stored["metadatas"]),
        key=lambda row: int(row[0].rsplit(":", 1)[1]),
    )
    labelled = bool(rows) and all((metadata or {}).get("label") for _, _, metadata in rows)
    if (reembed and not labelled) or (not reembed and labelled and not force):
        return "skipped"
    expected_ids = [f"{document_id}:chunk:{index}" for index in range(len(rows))]
    if [chunk_id for chunk_id, _, _ in rows] != expected_ids:
        raise ValueError("chunk IDs are not a contiguous <document_id>:chunk:<index> sequence")

    chunks = [document for _, document, _ in rows]
    label_fn = label_document
    if reembed:
        title = (rows[0][2] or {}).get("document_title") or title_document(chunks)
        kept = DocumentLabels(title=title, labels=[metadata["label"] for _, _, metadata in rows])
        label_fn = lambda _chunks: kept
    payload = prepare_index_payload(document_id, chunks, label_fn)
    replace_index_payload(document_id, payload)
    return "reembedded" if reembed else "reindexed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-index stored documents in place: label them, or re-embed them.")
    parser.add_argument("document_ids", nargs="*", help="Documents to re-index.")
    parser.add_argument("--all", action="store_true", help="Re-index every document in the local store.")
    parser.add_argument("--force", action="store_true", help="Relabel documents that already have labels.")
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Only re-embed with the current embedding model, reusing stored labels.",
    )
    args = parser.parse_args(argv)
    if bool(args.all) == bool(args.document_ids):
        parser.error("pass document IDs or --all, not both")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    failures = 0
    for document_id in list_document_ids() if args.all else args.document_ids:
        try:
            outcome = reindex_document(document_id, force=args.force, reembed=args.reembed)
        except Exception as exc:
            failures += 1
            outcome = f"FAILED: {exc}"
        print(f"{document_id} {outcome}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
