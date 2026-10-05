"""Index eval PDFs into the local Chroma store, the same way an upload does.

This runs only the indexing half of `upload_document`: extract text, chunk it, and embed the
chunks under a new `document_id` (chunk IDs are `<document_id>:chunk:<index>`). It skips the
Supabase storage and metadata steps, so indexed PDFs don't appear in the app's library.

Results go to a local manifest mapping each PDF path and SHA-256 to its `document_id`. PDFs
whose SHA-256 is already in the manifest are skipped while their collection still holds chunks,
so reruns only index what's missing, including PDFs whose Chroma store was cleared.

    .venv/bin/python -m backend.scripts.index_eval_documents \
        --corpus evals/financial-filings/manifest.json \
        --output evals/financial-filings/indexed-documents.local.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.services.pdf_extractor import extract_text_from_pdf
from backend.services.text_chunker import chunk_text
from backend.services.vector_store import (
    build_vector_store,
    delete_vector_store,
    get_persisted_collection,
)


IndexFn = Callable[[bytes], dict[str, Any]]
CountFn = Callable[[str], int]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def index_pdf_bytes(data: bytes) -> dict[str, Any]:
    """Extract, chunk and embed one PDF exactly as `upload_document` does."""
    text = extract_text_from_pdf(data)
    chunks = [chunk.strip() for chunk in chunk_text(text) if chunk and chunk.strip()]
    if not chunks:
        raise ValueError("no usable text chunks")

    document_id = str(uuid.uuid4())
    try:
        stored_count = build_vector_store(document_id=document_id, chunks=chunks)
    except Exception:
        delete_vector_store(document_id)
        raise
    if stored_count == 0:
        delete_vector_store(document_id)
        raise ValueError("chunks were created but none were stored")
    return {"document_id": document_id, "chunk_count": len(chunks), "stored_count": stored_count}


def _collection_count(document_id: str) -> int:
    """Chunks stored for `document_id`; 0 if its collection no longer exists."""
    try:
        return get_persisted_collection(document_id).count()
    except Exception as exc:
        if "does not exist" in str(exc).lower():
            return 0
        raise


def index_documents(
    pdf_paths: list[str],
    manifest: dict[str, Any],
    *,
    index_fn: IndexFn = index_pdf_bytes,
    count_fn: CountFn = _collection_count,
    save: Callable[[dict[str, Any]], None] = lambda manifest: None,
) -> list[dict[str, str]]:
    """Add each PDF to `manifest["documents"]` unless its SHA-256 is there with a nonempty collection.

    An entry whose collection is gone or empty is dropped and the PDF indexed again. Calls `save`
    after every new entry so an interrupted run keeps its progress. Returns one failure record per
    PDF that could not be indexed.
    """
    documents: list[dict[str, Any]] = manifest.setdefault("documents", [])
    failures: list[dict[str, str]] = []

    for path in pdf_paths:
        data = Path(path).read_bytes()
        sha256 = _sha256(data)
        entry = next((entry for entry in documents if entry["sha256"] == sha256), None)
        if entry is not None:
            if count_fn(entry["document_id"]) > 0:
                print(f"skip   {path} (already in manifest)", file=sys.stderr)
                continue
            print(f"stale  {path}: collection {entry['document_id']} is empty, indexing again", file=sys.stderr)
            documents.remove(entry)

        try:
            result = index_fn(data)
        except Exception as exc:
            print(f"FAIL   {path}: {exc}", file=sys.stderr)
            failures.append({"path": path, "error": str(exc)})
            continue

        documents.append({"path": path, "sha256": sha256, "origin": "indexed", **result})
        save(manifest)
        print(f"indexed {path} -> {result['document_id']} ({result['stored_count']} chunks)", file=sys.stderr)

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index eval PDFs into the local Chroma store.")
    parser.add_argument("--corpus", required=True, help="Corpus manifest listing PDFs under `documents[].path`.")
    parser.add_argument("--output", required=True, help="Local manifest of indexed documents (created or extended).")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    try:
        corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
        pdf_paths = [entry["path"] for entry in corpus["documents"]]
        output = Path(args.output)
        manifest = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    except (OSError, KeyError, ValueError) as exc:
        print(f"Indexing failed: {exc}", file=sys.stderr)
        return 1

    def save(current: dict[str, Any]) -> None:
        output.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")

    failures = index_documents(pdf_paths, manifest, save=save)
    save(manifest)
    print(f"{len(manifest['documents'])} documents in {output}; {len(failures)} failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
