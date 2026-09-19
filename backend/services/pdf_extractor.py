from io import BytesIO
from typing import List

import pdfplumber


def extract_pdf_pages(data: bytes) -> List[str]:
    """Extract one text value per PDF page using the application's PDF parser."""
    if not data:
        return []

    pages: List[str] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)

    return pages


def extract_text_from_pdf(data: bytes) -> str:
    """Return the same page-joined text used by document ingestion."""
    pages = [page for page in extract_pdf_pages(data) if page]

    return "\n\n".join(pages).strip()
