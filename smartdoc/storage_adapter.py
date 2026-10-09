"""Local adapter with relative references and atomic individual file writes."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from .config import storage_root

class LocalStorage:
    def __init__(self, root=None):
        self.root = Path(root or storage_root()).resolve()

    def resolve(self, reference):
        path = (self.root / reference).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Storage reference is outside the configured root.')
        return path

    def write(self, reference, payload):
        target = self.resolve(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with NamedTemporaryFile(dir=target.parent, delete=False) as f:
                tmp = Path(f.name); f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, target)
        finally:
            if tmp is not None: tmp.unlink(missing_ok=True)

    def read_text(self, reference):
        return self.resolve(reference).read_text(encoding='utf-8')

    def delete(self, reference):
        self.resolve(reference).unlink(missing_ok=True)
