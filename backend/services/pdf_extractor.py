from io import BytesIO
from typing import List

import pdfplumber


def extract_text_from_pdf(data: bytes) -> str:
    if not data:
        return ""

    pages: List[str] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                pages.append(text)

    return "\n\n".join(pages).strip()
