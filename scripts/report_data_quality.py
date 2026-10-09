"""Export read-only PostgreSQL corpus checks to CSV and JSON."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from smartdoc.config import PROJECT_ROOT
from smartdoc.db import connect
from smartdoc.ingestion import CORPUS_LOCK
from smartdoc.storage_adapter import LocalStorage
from smartdoc.data_quality import inspect_document, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT/'reports')
    args = parser.parse_args()
    # Coordinate with ingestion/deletion while reading metadata and storage.
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (CORPUS_LOCK,))
        revision = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()['revision']
        records = conn.execute('SELECT * FROM documents ORDER BY id').fetchall()
        rows = [inspect_document(row, LocalStorage()) for row in records]
    summary = summarize(rows, revision)
    summary['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fields = ['id','title','file_type','size_bytes','sha256','word_count','source_uri','source_status',
              'storage_ref','text_ref','created_at','ingest_status','error_message',
              'observed_token_count','storage_check','quality_issues',
              'preprocessing_version','preprocessing_config','processed_at','corpus_name','category','dataset_id']
    csv_path = args.output_dir/'data_quality_report.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            entry = dict(row)
            entry['preprocessing_config'] = json.dumps(entry['preprocessing_config'], ensure_ascii=False, sort_keys=True)
            writer.writerow(entry)
    json_path = args.output_dir/'data_quality_summary.json'
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Ready: {summary['ready_documents']}; records: {summary['total_records']}")
    print(f"Ready documents missing DB source: {summary['ready_missing_source']}")
    print(f"Ready documents with storage issues: {summary['ready_storage_issues']}")
    print('Duplicate upload count: unavailable (not logged).')
    print(f'CSV: {csv_path}\nSummary: {json_path}')

if __name__ == '__main__': main()
