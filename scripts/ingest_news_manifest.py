"""Validate a prepared manifest completely before importing its documents."""
import argparse
import hashlib
import json
from pathlib import Path
from collections import Counter
from smartdoc.config import PROJECT_ROOT
from smartdoc.ingestion import ingest_document
from smartdoc.db import connect

CORPUS = 'vietonline_news_200'

def validate_manifest(folder):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['dataset'] != 'VLUS06/VietOnlineNews': raise ValueError('Unexpected dataset.')
    rows = manifest['documents']
    if len(rows) != manifest['document_count']: raise ValueError('Manifest count mismatch.')
    seen = set()
    for row in rows:
        filename = row['filename']
        if Path(filename).name != filename: raise ValueError('Invalid filename.')
        if row['dataset_id'] in seen: raise ValueError('Duplicate dataset ID.')
        seen.add(row['dataset_id'])
        payload = (folder/filename).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row['sha256']: raise ValueError(f'Hash mismatch: {filename}')
        if not row['title'].strip() or not row['category'].strip(): raise ValueError('Missing title or category.')
        payload.decode('utf-8')
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path,nargs='?',default=PROJECT_ROOT/'data/raw/vietonline_news/selected_200')
    args=p.parse_args()
    rows=validate_manifest(args.folder)
    counts=Counter()
    for row in rows:
        result=ingest_document(args.folder/row['filename'],row['source_uri'],title=row['title'],
                               corpus_name=CORPUS,category=row['category'],dataset_id=row['dataset_id'])
        counts[result['status']]+=1
        if result['status']=='duplicate':
            with connect() as c:
                existing=c.execute('SELECT corpus_name,category,dataset_id,title,source_uri,ingest_status FROM documents WHERE id=%s',(result['document_id'],)).fetchone()
            expected=dict(corpus_name=CORPUS,category=row['category'],dataset_id=row['dataset_id'],title=row['title'],source_uri=row['source_uri'],ingest_status='ready')
            if existing != expected: raise ValueError('Duplicate belongs to incompatible metadata; resolve it explicitly.')
        if result['status']=='failed': print(json.dumps({'filename':row['filename'],**result},ensure_ascii=False))
    print(json.dumps({'corpus':CORPUS,'results':dict(counts)},ensure_ascii=False))
    if counts['failed']: p.exit(1,'Some documents failed; successful imports remain committed.\n')

if __name__=='__main__': main()
