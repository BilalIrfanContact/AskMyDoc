"""Read-only inspection of an already-indexed document."""

from __future__ import annotations

import os
import re
from typing import Any

from .authz import require_user_document
from .markdown_extractor import extract_text_from_markdown
from .pdf_extractor import extract_pdf_pages
from .persistence import PersistenceError
from .persistence.storage_repository import download_storage_object
from .text_chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_text
from .vector_store import get_persisted_collection


_CHUNK_INDEX_PATTERN = re.compile(r":chunk:(\d+)$")


def _token_counter():
    try:
        import tiktoken

        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        try:
            return tiktoken.encoding_for_model(model), model
        except KeyError:
            return tiktoken.get_encoding("cl100k_base"), "cl100k_base"
    except Exception:
        return None, None


def _token_count(text: str, encoder: Any) -> int | None:
    if encoder is None:
        return None
    return len(encoder.encode(text))


def _overlap_characters(previous: str | None, current: str) -> int:
    if not previous or not current:
        return 0

    maximum = min(len(previous), len(current))
    for size in range(maximum, 0, -1):
        if previous.endswith(current[:size]):
            return size
    return 0


def _chunk_index(chunk_id: str, metadata: dict[str, Any]) -> int | None:
    value = metadata.get("chunk_index")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)

    match = _CHUNK_INDEX_PATTERN.search(chunk_id)
    return int(match.group(1)) if match else None


def _source_pages(filename: str, data: bytes) -> tuple[str, list[str], list[tuple[int, str]]]:
    if filename.lower().endswith(".pdf"):
        pages = extract_pdf_pages(data)
        extracted_pages = [
            (page_number, page)
            for page_number, page in enumerate(pages, start=1)
            if page
        ]
        return "pdf", pages, extracted_pages

    text = extract_text_from_markdown(data)
    return "markdown", [text] if text else [], [(1, text)] if text else []


def _joined_text_with_page_spans(pages: list[tuple[int, str]]) -> tuple[str, list[dict[str, int]]]:
    joined = "\n\n".join(page for _, page in pages)
    text = joined.strip()
    leading_whitespace = len(joined) - len(joined.lstrip())
    spans: list[dict[str, int]] = []
    cursor = 0

    for page_number, page in pages:
        start = text.find(page, max(0, cursor - leading_whitespace))
        if start < 0:
            continue
        end = start + len(page)
        spans.append({"page_number": page_number, "start": start, "end": end})
        cursor = end + 2

    return text, spans


def _repeated_page_lines(pages: list[tuple[int, str]]) -> list[str]:
    """Find short lines repeated across pages, which are likely page furniture."""
    line_pages: dict[str, set[int]] = {}
    for page_number, page in pages:
        for raw_line in page.splitlines():
            line = raw_line.strip()
            if len(line) < 10 or len(line) > 100:
                continue
            line_pages.setdefault(line, set()).add(page_number)

    return [line for line, page_numbers in sorted(line_pages.items(), key=lambda item: (-len(item[1]), item[0])) if len(page_numbers) >= 2][:5]


def _page_location(text: str, source_text: str, page_spans: list[dict[str, int]], search_from: int) -> tuple[int | None, int | None, int | None]:
    if not text:
        return None, None, None

    start = source_text.find(text, max(0, search_from))
    if start < 0 and search_from:
        start = source_text.find(text)
    if start < 0:
        return None, None, None

    end = start + len(text)
    pages = [span["page_number"] for span in page_spans if span["start"] < end and span["end"] > start]
    if not pages:
        return start, end, None
    return start, end, pages[0] if len(pages) == 1 else pages[-1]


def _failed_report(document: dict[str, Any], warning: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "document": {
            "id": document.get("id"),
            "filename": document.get("filename"),
            "uploaded_at": document.get("uploaded_at"),
        },
        "source": {"type": None, "pages": [], "extracted_text": "", "character_count": 0},
        "chunks": [],
        "warnings": [warning],
    }


def inspect_document_chunks(document_id: str, user_id: str) -> dict[str, Any]:
    """Build a read-only report for a document owned by ``user_id``.

    This deliberately opens Chroma's persisted collection directly so the
    inspection never constructs an embedding model or writes to the index.
    """
    document = require_user_document(document_id=document_id, user_id=user_id)
    filename = str(document.get("filename") or "document")
    warnings: list[str] = []

    try:
        data = download_storage_object(str(document.get("storage_url") or ""))
    except PersistenceError:
        return _failed_report(document, "The source document could not be downloaded for inspection.")

    try:
        source_type, all_pages, non_empty_pages = _source_pages(filename, data)
    except Exception:
        return _failed_report(document, "The source document could not be extracted with the existing parser.")

    source_text, page_spans = _joined_text_with_page_spans(non_empty_pages)
    if not source_text:
        warnings.append("The existing extractor returned no text.")

    derived_chunks = [chunk.strip() for chunk in chunk_text(source_text) if chunk and chunk.strip()]
    if source_type == "pdf":
        if not non_empty_pages:
            warnings.append("No non-empty PDF pages were extracted.")
        repeated_lines = _repeated_page_lines(non_empty_pages)
        if repeated_lines:
            warnings.append(
                "Repeated page lines may pollute chunks: "
                + "; ".join(repr(line) for line in repeated_lines)
                + "."
            )
        warnings.append(
            "Chroma metadata has no stored page locations; page ranges below are derived by matching chunk text to the source extraction."
        )
    else:
        warnings.append("This document has no PDF page metadata; its source is represented as one text section.")
    warnings.append("Heading metadata is not stored; headings remain part of the exact chunk text.")

    try:
        collection = get_persisted_collection(document_id)
        stored = collection.get(include=["documents", "metadatas"])
    except Exception:
        return _failed_report(document, "The persisted Chroma collection could not be read.")

    ids = stored.get("ids") or []
    texts = stored.get("documents") or []
    metadatas = stored.get("metadatas") or []
    rows = []
    for position, chunk_id in enumerate(ids):
        metadata = metadatas[position] if position < len(metadatas) and metadatas[position] else {}
        rows.append(
            {
                "id": chunk_id,
                "text": texts[position] if position < len(texts) and texts[position] is not None else "",
                "metadata": metadata,
                "chunk_index": _chunk_index(chunk_id, metadata),
            }
        )

    if any(row["chunk_index"] is None for row in rows):
        warnings.append("One or more stored chunks have no usable chunk index metadata.")
    rows.sort(key=lambda row: row["chunk_index"] if row["chunk_index"] is not None else float("inf"))

    encoder, token_encoding = _token_counter()
    if encoder is None:
        warnings.append("Token counts are unavailable because tiktoken is not installed.")

    if len(derived_chunks) != len(rows):
        warnings.append(
            f"The current extraction/chunking pass produced {len(derived_chunks)} chunks, while Chroma contains {len(rows)}."
        )

    chunks: list[dict[str, Any]] = []
    spanning_chunks: list[int] = []
    previous_text: str | None = None
    search_from = 0
    for order, row in enumerate(rows):
        text = row["text"]
        start, end, page_end = _page_location(text, source_text, page_spans, search_from)
        page_start = page_end
        if start is None:
            warnings.append(f"Could not map stored chunk {row['id']} back to the extracted source text.")
        else:
            overlapping_pages = [
                span["page_number"]
                for span in page_spans
                if span["start"] < end and span["end"] > start
            ]
            if overlapping_pages:
                page_start = overlapping_pages[0]
                page_end = overlapping_pages[-1]
                if page_start != page_end:
                    spanning_chunks.append(order)
            search_from = max(start + 1, search_from)

        derived_match = order < len(derived_chunks) and derived_chunks[order] == text
        if order < len(derived_chunks) and not derived_match:
            warnings.append(f"Stored chunk {row['id']} differs from the current extraction/chunking result.")

        chunks.append(
            {
                "order": order,
                "id": row["id"],
                "text": text,
                "metadata": row["metadata"],
                "character_count": len(text),
                "token_count": _token_count(text, encoder),
                "overlap_character_count": _overlap_characters(previous_text, text),
                "page_start": page_start,
                "page_end": page_end,
                "source_character_start": start,
                "source_character_end": end,
                "matches_current_chunking": derived_match,
            }
        )
        previous_text = text

    if spanning_chunks:
        warnings.append(
            "Chunks spanning multiple source pages require review for page-boundary and table-context splits: "
            + ", ".join(str(index) for index in spanning_chunks)
            + "."
        )

    page_reports = [
        {
            "page_number": index,
            "text": page,
            "character_count": len(page),
        }
        for index, page in enumerate(all_pages, start=1)
    ]

    return {
        "status": "ready_with_warnings" if warnings else "ready",
        "document": {
            "id": document.get("id"),
            "filename": filename,
            "uploaded_at": document.get("uploaded_at"),
        },
        "source": {
            "type": source_type,
            "pages": page_reports,
            "extracted_text": source_text,
            "character_count": len(source_text),
        },
        "chunking": {
            "chunk_count_from_current_pass": len(derived_chunks),
            "stored_chunk_count": len(chunks),
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "configured_overlap": DEFAULT_CHUNK_OVERLAP,
            "token_encoding": token_encoding,
            "chunks_spanning_pages": spanning_chunks,
        },
        "chunks": chunks,
        "warnings": warnings,
    }
