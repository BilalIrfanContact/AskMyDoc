import re
from io import BytesIO
from typing import Any, Iterable, List

import pdfplumber


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _serialize_table(rows: list[list[Any]]) -> str | None:
    """Serialize a table only when its first row is a usable header."""
    if len(rows) < 3:
        return None

    normalized = [[_clean_cell(cell) for cell in row] for row in rows]
    first_content_index = next(
        (index for index, row in enumerate(normalized) if any(row)),
        None,
    )
    if (
        first_content_index is None
        or sum(bool(cell) for cell in normalized[first_content_index]) < 2
    ):
        return None

    header = normalized[first_content_index]
    column_count = len(header)
    if column_count < 2:
        return None

    data_rows = normalized[first_content_index + 1 :]
    usable_rows = [row for row in data_rows if sum(bool(cell) for cell in row) >= 2]
    if len(usable_rows) < 2:
        return None

    first_header = header[0].lower()
    carry_first_column = first_header in {"year", "date", "period"}
    previous_first_value = ""
    serialized = [" | ".join(header[:column_count])]
    serialized.append(" | ".join("---" for _ in range(column_count)))

    for row in data_rows:
        cells = (row + [""] * column_count)[:column_count]
        if carry_first_column:
            if cells[0]:
                previous_first_value = cells[0]
            elif previous_first_value and any(cells[1:]):
                cells[0] = previous_first_value
        if sum(bool(cell) for cell in cells) >= 2:
            serialized.append(" | ".join(cells))

    return "\n".join(serialized) if len(serialized) > 2 else None


def _inside_bbox(word: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    word_center_x = (word["x0"] + word["x1"]) / 2
    word_center_top = (word["top"] + word["bottom"]) / 2
    return x0 <= word_center_x <= x1 and top <= word_center_top <= bottom


def _word_lines(words: Iterable[dict[str, Any]]) -> list[tuple[float, str]]:
    lines: list[dict[str, Any]] = []
    for word in words:
        for line in lines:
            if abs(word["top"] - line["top"]) <= 3:
                line["words"].append(word)
                break
        else:
            lines.append({"top": word["top"], "words": [word]})

    result = []
    for line in sorted(lines, key=lambda item: item["top"]):
        line_text = " ".join(word["text"] for word in sorted(line["words"], key=lambda item: item["x0"]))
        result.append((line["top"], _normalize_line(line_text)))
    return result


def _normalize_line(text: str) -> str:
    text = re.sub(r"\(\s+(?=\d)", "(", text)
    return re.sub(r"(?<=\d)\s+%(?!\w)", "%", text)


def _structured_tables(page: Any) -> list[tuple[tuple[float, float, float, float], str]]:
    tables: list[tuple[tuple[float, float, float, float], str]] = []
    try:
        candidates = page.find_tables()
    except Exception:
        return tables

    for table in candidates:
        try:
            serialized = _serialize_table(table.extract())
        except Exception:
            continue
        if serialized:
            tables.append((table.bbox, serialized))
    return tables


def _extract_page_text(page: Any) -> str:
    """Extract layout-aware text while preserving usable table rows."""
    tables = _structured_tables(page)
    table_bboxes = [bbox for bbox, _text in tables]
    words = page.extract_words(use_text_flow=True)
    blocks: list[tuple[float, str]] = _word_lines(
        word for word in words if not any(_inside_bbox(word, bbox) for bbox in table_bboxes)
    )
    blocks.extend((bbox[1], text) for bbox, text in tables)
    blocks.sort(key=lambda item: item[0])
    return "\n".join(text for _top, text in blocks).strip()


def extract_pdf_pages(data: bytes) -> List[str]:
    """Extract one text value per PDF page using the application's PDF parser."""
    if not data:
        return []

    pages: List[str] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = _extract_page_text(page)
            pages.append(text)

    return pages


def extract_text_from_pdf(data: bytes) -> str:
    """Return the same page-joined text used by document ingestion."""
    pages = [page for page in extract_pdf_pages(data) if page]

    return "\n\n".join(pages).strip()
