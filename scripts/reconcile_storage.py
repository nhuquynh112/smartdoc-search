"""Report orphan files; optionally move them to quarantine without deleting them."""
import argparse
import json
from smartdoc.config import PROJECT_ROOT
from smartdoc.recovery import reconcile_storage

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quarantine',action='store_true',help='Move unreferenced files into storage/quarantine. No files are deleted.')
    args=parser.parse_args()
    report=reconcile_storage(quarantine=args.quarantine)
    output=PROJECT_ROOT/'reports/storage_recovery.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"Orphans: {len(report['orphan_files'])}; quarantined: {len(report['quarantined'])}; missing references: {len(report['missing_references'])}")
    print(f"Pending IDs: {report['pending_document_ids']}; errors: {len(report['errors'])}")
    print(f'Report: {output}')

if __name__=='__main__':main()
