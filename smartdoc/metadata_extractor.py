"""Metadata derived from file bytes; unknown provenance stays absent."""
import hashlib
from pathlib import Path

def extract_metadata(path: str | Path, source_uri: str | None = None, *, payload: bytes | None = None) -> dict:
    path = Path(path)
    payload = path.read_bytes() if payload is None else payload
    return {
        'title': path.stem,
        'file_type': path.suffix.lower().lstrip('.'),
        'size_bytes': len(payload),
        'sha256': hashlib.sha256(payload).hexdigest(),
        'source_uri': source_uri,
    }
