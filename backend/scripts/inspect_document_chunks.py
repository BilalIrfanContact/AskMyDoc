"""Inspect an owned, already-indexed document without changing application state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.bootstrap import initialize_backend_environment
from backend.services.chunk_inspector import inspect_document_chunks
from backend.services.persistence import PersistenceError
from backend.services.persistence.documents_repository import list_user_documents


def _write_json(value: Any, output: str | None) -> None:
    rendered = json.dumps(value, indent=2, ensure_ascii=False)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote inspection report to {output}")
    else:
        print(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only inspection of an AskMyDoc document's extraction and Chroma chunks."
    )
    parser.add_argument("--user-id", required=True, help="The owner identity used by the existing document authorization check.")
    parser.add_argument("--document-id", help="The already-ingested document to inspect.")
    parser.add_argument("--list", action="store_true", help="List this user's documents so one can be selected.")
    parser.add_argument("--output", help="Write the JSON report to this local path instead of stdout.")
    args = parser.parse_args(argv)

    initialize_backend_environment()

    if args.list:
        try:
            documents = list_user_documents(user_id=args.user_id)
        except PersistenceError:
            _write_json({"status": "failed", "warnings": ["Could not list the user's documents."]}, args.output)
            return 1
        _write_json({"status": "ready", "documents": documents}, args.output)
        return 0

    if not args.document_id:
        parser.error("--document-id is required unless --list is used")

    try:
        report = inspect_document_chunks(document_id=args.document_id, user_id=args.user_id)
    except Exception as exc:
        # Keep backend/storage details out of the CLI output; the report is allowed
        # to contain document text only because the operator explicitly requested it.
        _write_json({"status": "failed", "warnings": [f"Inspection failed: {type(exc).__name__}."]}, args.output)
        return 1

    _write_json(report, args.output)
    return 0 if report.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
