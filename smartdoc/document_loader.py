"""Strict UTF-8 TXT and text-layer PDF extraction."""
from pathlib import Path
from io import BytesIO
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_EXTRACTED_CHARACTERS = 2_000_000

class DocumentLoadError(ValueError):
    """Input cannot supply valid searchable text."""

def load_document(path: str | Path) -> str:
    source = Path(path)
    if not source.is_file():
        raise DocumentLoadError('Document does not exist or is not a file.')
    suffix = source.suffix.lower()
    if suffix not in {'.txt', '.pdf'}:
        raise DocumentLoadError('Only TXT and PDF documents are supported.')
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise DocumentLoadError('Document could not be read.') from exc
    return load_document_bytes(payload, suffix)


def load_document_bytes(payload: bytes, suffix: str) -> str:
    """Extract from an immutable byte snapshot shared with metadata/storage."""
    suffix = suffix.lower()
    if suffix not in {'.txt', '.pdf'}:
        raise DocumentLoadError('Only TXT and PDF documents are supported.')
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise DocumentLoadError('Document exceeds the 8 MB processing limit.')
    try:
        if suffix == '.txt':
            text = payload.decode('utf-8-sig')
        else:
            reader = PdfReader(BytesIO(payload))
            if reader.is_encrypted:
                raise DocumentLoadError('Encrypted PDFs are not supported.')
            if len(reader.pages) > MAX_PDF_PAGES:
                raise DocumentLoadError(f'PDF exceeds the {MAX_PDF_PAGES}-page processing limit.')
            parts, characters = [], 0
            for page in reader.pages:
                part = page.extract_text() or ''
                characters += len(part) + bool(parts)
                if characters > MAX_EXTRACTED_CHARACTERS:
                    raise DocumentLoadError('Extracted text exceeds the processing limit.')
                parts.append(part)
            text = '\n'.join(parts)
    except DocumentLoadError:
        raise
    except (OSError, UnicodeError, PdfReadError, ValueError) as exc:
        raise DocumentLoadError('Document could not be decoded or extracted.') from exc
    if not text.strip():
        message = 'PDF has no extractable text; OCR is not supported.' if suffix == '.pdf' else 'Document is empty.'
        raise DocumentLoadError(message)
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise DocumentLoadError('Extracted text exceeds the processing limit.')
    if '\x00' in text:
        raise DocumentLoadError('Document contains NUL characters; verify its encoding.')
    return text
