"""Create a custom-format DB backup through Docker without host pg_dump."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from smartdoc.config import PROJECT_ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=PROJECT_ROOT/'reports/smartdoc.dump')
    args=p.parse_args()
    if args.output.exists(): p.error('Backup exists; choose a new --output path.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix(args.output.suffix+'.tmp')
    try:
        with temp.open('xb') as f:
            subprocess.run(['docker','compose','exec','-T','db','sh','-c',
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl'],
                cwd=PROJECT_ROOT,stdout=f,check=True)
        with temp.open('rb') as f:
            subprocess.run(['docker','compose','exec','-T','db','pg_restore','--list'],
                           cwd=PROJECT_ROOT,stdin=f,stdout=subprocess.DEVNULL,check=True)
        os.replace(temp,args.output)
    finally:
        temp.unlink(missing_ok=True)
    digest=hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest={'format':'postgresql-custom','sha256':digest,'size_bytes':args.output.stat().st_size,
              'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'includes':['schema','metadata','raw_text','clean_text','corpus_state'],
              'excludes':['database_roles','role_passwords','original_files','index_artifacts']}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Backup verified: {args.output}')
    print('Share the dump and its manifest privately with your team.')

if __name__=='__main__': main()
