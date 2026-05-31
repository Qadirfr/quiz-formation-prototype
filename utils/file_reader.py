from __future__ import annotations

from io import BytesIO
from typing import Optional

import docx
from PyPDF2 import PdfReader


def read_uploaded_file(uploaded_file) -> str:
    """Read Streamlit uploaded files: txt, md, docx, pdf."""
    if uploaded_file is None:
        return ""

    filename = uploaded_file.name.lower()
    raw = uploaded_file.read()

    if filename.endswith((".txt", ".md")):
        return raw.decode("utf-8", errors="ignore")

    if filename.endswith(".docx"):
        document = docx.Document(BytesIO(raw))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())

    if filename.endswith(".pdf"):
        reader = PdfReader(BytesIO(raw))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    raise ValueError("Format non supporté. Utilise TXT, MD, DOCX ou PDF.")


def clean_training_text(text: Optional[str]) -> str:
    """Normalize whitespace while preserving paragraphs."""
    if not text:
        return ""
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    cleaned = []
    previous_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        cleaned.append(line)
        previous_blank = is_blank
    return "\n".join(cleaned).strip()
