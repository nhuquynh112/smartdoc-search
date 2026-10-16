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
    manifest_path=args.output.with_name(args.output.name+'.manifest.json')
    # Acquire ownership before entering cleanup: a competing backup owns any
    # existing temporary file and must be the only process allowed to remove it.
    stream=temp.open('xb')
    try:
        with stream as f:
            # Recheck after acquisition in case another backup finished since
            # the initial existence check. Never replace its archive/manifest.
            if args.output.exists() or manifest_path.exists():
                p.error('Backup or manifest exists; choose a new --output path.')
            subprocess.run(['docker','compose','exec','-T','db','sh','-c',
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl'],
                cwd=PROJECT_ROOT,stdout=f,check=True)
        with temp.open('rb') as f:
            subprocess.run(['docker','compose','exec','-T','db','pg_restore','--list'],
                           cwd=PROJECT_ROOT,stdin=f,stdout=subprocess.DEVNULL,check=True)
        # Publish without overwriting an existing destination, while retaining
        # our temporary path until cleanup so ownership cannot change midway.
        os.link(temp,args.output)
        digest=hashlib.sha256(args.output.read_bytes()).hexdigest()
        manifest={'format':'postgresql-custom','sha256':digest,'size_bytes':args.output.stat().st_size,
                  'created_at_utc':datetime.now(timezone.utc).isoformat(),
                  'includes':['schema','metadata','raw_text','clean_text','corpus_state'],
                  'excludes':['database_roles','role_passwords','original_files','index_artifacts']}
        with manifest_path.open('x',encoding='utf-8') as f:
            f.write(json.dumps(manifest,indent=2)+'\n')
    finally:
        temp.unlink(missing_ok=True)
    print(f'Backup verified: {args.output}')
    print('Share the dump and its manifest privately with your team.')

if __name__=='__main__': main()
