"""Import a single file or a directory of TXT/PDF files."""
import argparse
import json
from pathlib import Path
from smartdoc.ingestion import ingest_document

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--source-uri', help='Known source, for a single document only.')
    parser.add_argument('--retry-failed', action='store_true', help='Retry the same file hash and retain the failed record ID/metadata.')
    args = parser.parse_args()
    if not args.path.exists(): parser.error('Input path does not exist.')
    if args.path.is_dir() and args.source_uri: parser.error('Use --source-uri with a single file.')
    files = sorted(p for p in args.path.rglob('*') if p.is_file() and p.suffix.lower() in {'.txt','.pdf'}) if args.path.is_dir() else [args.path]
    failures = 0
    for path in files:
        try: result = ingest_document(path, args.source_uri, retry_failed=args.retry_failed)
        except (OSError, ValueError) as exc: result = {'status':'failed', 'error':str(exc)}
        failures += result['status'] == 'failed'
        print(json.dumps({'file':str(path), **result}, ensure_ascii=False))
    if not files: parser.exit(1, 'No supported files found.\n')
    if failures: parser.exit(1)

if __name__ == '__main__': main()
