"""Restore a trusted team backup into an empty public schema; never overwrite data."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from smartdoc.config import PROJECT_ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('backup',type=Path)
    args=p.parse_args()
    manifest_path=args.backup.with_name(args.backup.name+'.manifest.json')
    try:
        manifest_text=manifest_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        # Older team backups used a suffix-replacing sidecar name. Only fall
        # back when the new sidecar is absent, never on invalid data/checksums.
        manifest_text=args.backup.with_suffix('.manifest.json').read_text(encoding='utf-8')
    manifest=json.loads(manifest_text)
    if hashlib.sha256(args.backup.read_bytes()).hexdigest()!=manifest['sha256']:
        p.error('Backup checksum mismatch.')
    # Check the actual Compose target, not a possibly different host DATABASE_URL.
    probe=subprocess.run(['docker','compose','exec','-T','db','sh','-c',
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=\'public\' AND c.relkind IN (\'r\',\'p\',\'v\',\'m\',\'S\',\'f\');"'],
        cwd=PROJECT_ROOT,capture_output=True,text=True,check=True)
    if probe.stdout.strip()!='0': p.error('Target public schema is not empty. No data changed. Use a fresh database.')
    with args.backup.open('rb') as f:
        subprocess.run(['docker','compose','exec','-T','db','sh','-c',
            'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error --single-transaction'],
            cwd=PROJECT_ROOT,stdin=f,check=True)
    print('Restore completed. Run python -m scripts.check_db and verify the news snapshot.')
    print('Original-file references require the separate storage folder for file downloads.')

if __name__=='__main__': main()
