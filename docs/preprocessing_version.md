# Preprocessing Version Lifecycle

Each ready document stores `preprocessing_version`, a SHA-256 fingerprint of canonical settings, `preprocessing_config` (JSONB), and `processed_at`.

The manifest covers normalization rules, Unicode database, segmentation, Underthesea/core versions, PDF extraction dependencies, stopword toggle and sorted stopword contents. Increment `rules_version` when changing the preprocessing or extraction rules. The fingerprint is a declared configuration identifier, not a hash of all source code or proof of linguistic accuracy.

Upgrade existing databases and corpus:

```bash
python -m scripts.init_db
python -m scripts.reprocess_corpus
python -m scripts.export_corpus
```

Initialization applies additive, idempotent migrations. Existing records remain unknown until reprocessed; no version is fabricated for historical text. New ingestion stores the manifest automatically.

Reprocessing validates original hashes and writes new processed files without overwriting old ones. Metadata switches within a single transaction and corpus revision increments once if any ready document is updated. Failure before commit rolls back database changes; original and old processed files remain available. New unused files may remain after failure. Old files are retained for recovery and require later reconciliation. A second run with an unchanged manifest updates zero documents and does not increment revision.

Snapshot loading/export rejects ready records with unknown, mixed or outdated manifests. TV2 must save snapshot `preprocessing` and `corpus_revision` with its index. Before transforming a query, compare `pipeline_manifest()['fingerprint']` with the index's preprocessing fingerprint; reject mismatches and request reprocessing/rebuild. Do not fit queries independently.

Changing corpus preprocessing does not automatically rebuild TV2 artifacts or send notifications. After a successful reprocess, share a new export and tell TV2 to rebuild. The command prints that instruction. This workflow currently uses the default configuration; custom stopword profiles require coordinated changes to ingestion, reprocessing and query handling.
