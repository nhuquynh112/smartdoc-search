# Transfer the Database to a Teammate

A PostgreSQL dump includes the schema, all document metadata, raw text, clean text, preprocessing manifests and corpus revision. It excludes database roles/passwords, original files and TV2 index artifacts. The receiver uses their own local credentials. Transfer only trusted team-generated dumps; restoring a dump executes SQL. Share dataset text privately under the applicable source terms.

## TV1: create the package

With Docker PostgreSQL running:

```bash
python -m scripts.backup_database
```

Send both `reports/smartdoc.dump` and `reports/smartdoc.dump.manifest.json`. These files are ignored by Git. The script refuses to replace an existing backup; use `--output reports/smartdoc_v2.dump` for the next version. Each archive keeps its full filename in the manifest name, so `snapshot.dump` and `snapshot.backup` have separate manifests. Restore also accepts the legacy `smartdoc.manifest.json` name when the new sidecar is absent; a checksum failure never falls back to the legacy file. If a `.tmp` file already exists, backup stops without deleting it. Confirm its writer has stopped before handling a leftover temporary file. Backups preserve IDs and revision consistently using PostgreSQL's snapshot behavior.

## Teammate: restore on Ubuntu or Windows

1. Obtain the latest code and install `requirements.txt` in a virtual environment.
2. Copy `.env.example` to `.env`; set the local password in both places.
3. Start Docker with `docker compose up -d --wait`.
4. Put the dump and matching manifest in `reports/`.
5. Do **not** run `scripts.init_db` before restoring: restore requires an empty database schema.
6. Run:

```bash
python -m scripts.restore_database reports/smartdoc.dump
python -m scripts.check_db
python -m scripts.export_corpus --corpus vietonline_news_200 --output reports/tv2_news_corpus.json
```

The restore command verifies the checksum and refuses a nonempty public schema. It never drops tables or uses `--clean`. If your local database already contains tables, retain it and arrange a separate fresh database/Compose environment rather than deleting work.

A successful restoration should have 200 ready news records. The revision must match the source snapshot at backup time. Live indexing and raw-text viewing read PostgreSQL and do not require the source files.

## Original files

Original-file downloading still requires copying TV1's `storage/originals/` to the receiver's configured storage root. Existing processed-text caches may be transferred for quality-report cache checks, but are not required for DB text reads. Sharing the DB dump does not make local storage references resolve automatically.

## Verification scope

Backup archive parsing and a restoration round trip into a temporary database were verified on Ubuntu. Windows commands follow the same Python/Docker workflow but still require verification on a teammate's machine.
