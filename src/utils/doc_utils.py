from io import BytesIO

SUPPORTED_EXTENSIONS = (".txt", ".md", ".docx", ".doc")
MAX_CHARS = 24000  # ~6k tokens — safe for Bedrock


def parse_document(file_storage) -> str:
    """
    Parse an uploaded file object (Flask FileStorage) and return its full text.
    Supports .txt, .md, and .docx/.doc files.
    Truncates to MAX_CHARS with a note when exceeded.
    """
    filename = file_storage.filename or ""
    ext = _ext(filename)

    if ext in (".txt", ".md"):
        raw = file_storage.read()
        text = raw.decode("utf-8", errors="replace")

    elif ext in (".docx", ".doc"):
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError(
                "python-docx is not installed. Run: pip install python-docx"
            )
        doc = Document(BytesIO(file_storage.read()))
        parts = []

        for para in doc.paragraphs:
            stripped = para.text.strip()
            if stripped:
                # Preserve heading style as markdown heading markers
                style = para.style.name if para.style else ""
                if "Heading 1" in style:
                    parts.append(f"# {stripped}")
                elif "Heading 2" in style:
                    parts.append(f"## {stripped}")
                elif "Heading 3" in style:
                    parts.append(f"### {stripped}")
                else:
                    parts.append(stripped)

        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        text = "\n".join(parts)

    else:
        # Fallback: try UTF-8 decode
        try:
            text = file_storage.read().decode("utf-8", errors="replace")
        except Exception:
            raise ValueError(
                f"Unsupported file type '{ext}'. Upload a .txt, .md, or .docx file."
            )

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[Document truncated — content above covers the full API spec]"

    return text


def _ext(filename: str) -> str:
    filename = filename.lower()
    for ext in (".docx", ".doc", ".txt", ".md"):
        if filename.endswith(ext):
            return ext
    idx = filename.rfind(".")
    return filename[idx:] if idx != -1 else ""
