# app/ingest/loaders.py
from pathlib import Path

SUPPORTED = {".md", ".txt", ".pdf", ".docx"}


def load_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"不支持的格式: {ext}（支持 {sorted(SUPPORTED)}）")
    if ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        from pypdf import PdfReader

        return "\n".join(
            page.extract_text() or "" for page in PdfReader(str(path)).pages
        )
    from docx import Document as Docx  # .docx

    return "\n".join(p.text for p in Docx(str(path)).paragraphs if p.text.strip())
