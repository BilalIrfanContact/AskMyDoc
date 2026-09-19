import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Iterable, List

import pdfplumber


@dataclass(frozen=True)
class _TableContext:
    header: tuple[str, ...]
    first_column_value: str
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class _StructuredTable:
    bbox: tuple[float, float, float, float]
    text: str
    context: _TableContext


_TABLE_HEADER_TERMS = {
    "category",
    "composition",
    "content",
    "diameter",
    "description",
    "fineness",
    "face value",
    "image",
    "mass",
    "minted",
    "notes",
    "role",
    "specification",
    "thickness",
    "title",
    "total weight",
    "type",
    "value",
    "year",
}


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _is_header_cell(cell: str) -> bool:
    normalized = re.sub(r"\[\d+\]", "", cell.lower())
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())
    return normalized in _TABLE_HEADER_TERMS or (
        normalized.endswith("s") and normalized[:-1] in _TABLE_HEADER_TERMS
    )


def _looks_like_table_header(row: list[str]) -> bool:
    return any(_is_header_cell(cell) for cell in row if cell)


def _can_inherit_table_context(
    table: Any,
    rows: list[list[Any]],
    previous_context: _TableContext | None,
) -> bool:
    if not previous_context:
        return False
    if not previous_context.bbox:
        return False

    normalized = [[_clean_cell(cell) for cell in row] for row in rows]
    first_content_row = next((row for row in normalized if any(row)), None)
    if first_content_row is None:
        return False

    column_count = len(previous_context.header)
    has_only_trailing_extra_cells = len(first_content_row) >= column_count and not any(
        first_content_row[column_count:]
    )
    previous_x0, _previous_top, previous_x1, _previous_bottom = previous_context.bbox
    current_x0, _current_top, current_x1, _current_bottom = table.bbox
    previous_width = previous_x1 - previous_x0
    current_width = current_x1 - current_x0
    overlap = max(0.0, min(previous_x1, current_x1) - max(previous_x0, current_x0))
    has_matching_horizontal_placement = (
        previous_width > 0
        and current_width > 0
        and overlap / min(previous_width, current_width) >= 0.75
    )
    return (
        has_only_trailing_extra_cells
        and has_matching_horizontal_placement
        and sum(bool(cell) for cell in first_content_row) >= 2
        and not _looks_like_table_header(first_content_row)
    )


def _serialize_table_with_context(
    rows: list[list[Any]],
    previous_context: _TableContext | None = None,
) -> tuple[str, _TableContext] | None:
    """Serialize a table and carry context into continuation pages."""
    if len(rows) < 3:
        return None

    normalized = [[_clean_cell(cell) for cell in row] for row in rows]
    first_content_index = next(
        (index for index, row in enumerate(normalized) if any(row)),
        None,
    )
    if first_content_index is None:
        return None

    first_content_row = normalized[first_content_index]
    has_header = (
        sum(bool(cell) for cell in first_content_row) >= 2
        and _looks_like_table_header(first_content_row)
    )
    if has_header:
        header = first_content_row
        data_start = first_content_index + 1
    elif previous_context:
        header = list(previous_context.header)
        data_start = first_content_index
    else:
        return None

    column_count = len(header)
    if column_count < 2:
        return None

    data_rows = normalized[data_start:]
    usable_rows = [row for row in data_rows if sum(bool(cell) for cell in row) >= 2]
    if len(usable_rows) < 2:
        return None

    carry_first_column = True
    previous_first_value = "" if has_header else previous_context.first_column_value
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

    if len(serialized) <= 2 or not previous_first_value:
        return None
    return "\n".join(serialized), _TableContext(tuple(header[:column_count]), previous_first_value)


def _serialize_table(rows: list[list[Any]]) -> str | None:
    """Serialize a standalone table for callers that do not need context."""
    result = _serialize_table_with_context(rows)
    return result[0] if result else None


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


def _structured_tables(
    page: Any,
    previous_context: _TableContext | None = None,
) -> list[_StructuredTable]:
    tables: list[_StructuredTable] = []
    try:
        candidates = page.find_tables()
    except Exception:
        return tables

    for index, table in enumerate(candidates):
        try:
            rows = table.extract()
            context = (
                previous_context
                if index == 0 and _can_inherit_table_context(table, rows, previous_context)
                else None
            )
            serialized_result = _serialize_table_with_context(rows, context)
        except Exception:
            continue
        if serialized_result:
            serialized, table_context = serialized_result
            table_context = _TableContext(
                table_context.header,
                table_context.first_column_value,
                table.bbox,
            )
            tables.append(_StructuredTable(table.bbox, serialized, table_context))
    return tables


def _extract_page_text_with_context(
    page: Any,
    previous_context: _TableContext | None = None,
) -> tuple[str, _TableContext | None]:
    """Extract one page and return context for a table continued on the next page."""
    tables = _structured_tables(page, previous_context)
    table_bboxes = [table.bbox for table in tables]
    words = page.extract_words(use_text_flow=True)
    blocks: list[tuple[float, str]] = _word_lines(
        word for word in words if not any(_inside_bbox(word, bbox) for bbox in table_bboxes)
    )
    blocks.extend((table.bbox[1], table.text) for table in tables)
    blocks.sort(key=lambda item: item[0])
    next_context = tables[-1].context if tables else None
    return "\n".join(text for _top, text in blocks).strip(), next_context


def _extract_page_text(page: Any) -> str:
    """Extract layout-aware text while preserving usable table rows."""
    text, _context = _extract_page_text_with_context(page)
    return text


def extract_pdf_pages(data: bytes) -> List[str]:
    """Extract one text value per PDF page using the application's PDF parser."""
    if not data:
        return []

    pages: List[str] = []
    table_context: _TableContext | None = None
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            text, table_context = _extract_page_text_with_context(page, table_context)
            pages.append(text)

    return pages


def extract_text_from_pdf(data: bytes) -> str:
    """Return the same page-joined text used by document ingestion."""
    pages = [page for page in extract_pdf_pages(data) if page]

    return "\n\n".join(pages).strip()
