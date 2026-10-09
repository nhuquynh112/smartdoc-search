# Ingestion and Storage Recovery

## Retry a failed input

```bash
python -m scripts.ingest_documents path/to/file.pdf --retry-failed
```

Only a failed record with the exact same SHA-256 is retried. Its ID and original metadata are preserved. A ready record remains a duplicate and is never overwritten. If file bytes change, the new hash is a new document. Success clears the previous error, writes DB raw/clean text, records the preprocessing manifest and increments corpus revision.

## Inspect storage

```bash
python -m scripts.reconcile_storage
```

The default is read-only. `reports/storage_recovery.json` lists orphan files, missing references, pending records and errors. All DB references are protected, including failed or pending records. The scanner checks only managed `originals/` and `processed/` directories, skips symlinks and `.gitkeep`, and coordinates with ingestion/reprocessing through the corpus lock. Historical processed-text caches may be legitimate unreferenced recovery copies.

## Quarantine instead of deleting

```bash
python -m scripts.reconcile_storage --quarantine
```

Unreferenced files move to `storage/quarantine/<run-id>/` while the lock is held. This does not delete file contents or change DB records or corpus revision. Keep quarantine until inspection is complete. A failed move is reported and the source remains. Missing referenced originals cannot be recreated from DB raw text as the exact original PDF; recover the original from a backup or source and verify its stored SHA-256.

## Failure behavior and limits

- Extraction/filesystem errors handled during ingestion become failed records and partial writes are cleaned up when possible.
- Retry preserves failed IDs; pending records are reported for explicit investigation rather than automatically promoted.
- Unexpected exceptions or DB failures roll back the transaction. Process interruption or ambiguous commit failure can leave unreferenced files; reconciliation reads committed DB references after obtaining the mutation lock.
- Reprocessing retains old text caches deliberately. Quarantine can remove these from active storage without deleting them.
- DB content is authoritative for indexing/viewing; cache loss does not prevent those reads. Missing originals still affect downloads and future extraction.
- Cleanup cannot recover a lost database or original files. Maintain DB backups and a separate original-file backup.

Tests simulate a processed-file write failure, verify cleanup and successful retry with the same ID, and verify read-only scanning followed by recoverable quarantine. Full power-loss and ambiguous DB commit scenarios are not simulated.
