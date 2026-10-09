"""Configuration paths are relative to the repository, not the shell directory."""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / '.env')

def database_url():
    value = os.getenv('DATABASE_URL')
    if not value or 'CHANGE_ME' in value:
        raise RuntimeError('Set DATABASE_URL in the local .env file.')
    return value

def storage_root():
    path = Path(os.getenv('STORAGE_ROOT', 'storage'))
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
