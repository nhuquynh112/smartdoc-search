"""Export a portable, read-only corpus handoff for TV2."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from importlib.metadata import version
from smartdoc.config import PROJECT_ROOT
from smartdoc.ingestion import load_corpus_snapshot


def validate_snapshot(snapshot):
    ids = []
    for row in snapshot['documents']:
        for field in ['document_id','title','clean_text','source_uri','storage_ref']:
            if field not in row: raise ValueError(f'Missing field: {field}')
        if not isinstance(row['document_id'], int) or row['document_id'] <= 0:
            raise ValueError('Document IDs must be positive integers.')
        if not isinstance(row['clean_text'], str) or not row['clean_text'].strip():
            raise ValueError('Every exported document must have searchable text.')
        ids.append(row['document_id'])
    if ids != sorted(set(ids)): raise ValueError('IDs must be unique and sorted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT/'reports'/'tv2_corpus.json')
    args = parser.parse_args()
    snapshot = load_corpus_snapshot()
    validate_snapshot(snapshot)
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    payload = {
        'format_version': 1,
        'exported_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot_sha256': hashlib.sha256(canonical).hexdigest(),
        'document_count': len(snapshot['documents']),
        'current_pipeline': {
            'tokenizer': 'underthesea', 'version': version('underthesea'),
            'unicode': 'NFC', 'lowercase': True, 'segment_words': True,
            'remove_stopwords': False,
        },
        'preprocessing_provenance': 'Per-document pipeline versions are not recorded; current_pipeline describes current code, not verified historical processing of every record.',
        **snapshot,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as handle:
            tmp = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, args.output)
    finally:
        if tmp: tmp.unlink(missing_ok=True)
    print(f"Exported {payload['document_count']} documents; revision {snapshot['corpus_revision']}")
    print(f'Output: {args.output}')
    print('Original PDFs and database credentials are not included.')

if __name__ == '__main__': main()
