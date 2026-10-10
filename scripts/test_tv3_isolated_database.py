"""Run mutation tests in a new disposable database, preserving the demo corpus.

Requires CREATEDB permission on the configured local PostgreSQL server.
Only the newly created database with this script's unique name is dropped.
"""
from __future__ import annotations

import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from smartdoc.config import PROJECT_ROOT, database_url


def demo_state(url):
    with psycopg.connect(url, connect_timeout=5) as conn:
        revision = conn.execute("SELECT revision FROM corpus_state WHERE singleton").fetchone()[0]
        ready = conn.execute("SELECT count(*) FROM documents WHERE ingest_status='ready'").fetchone()[0]
    return {"corpus_revision": revision, "ready_documents": ready}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-tests", action="store_true", help="Run the entire suite in the disposable database.")
    args = parser.parse_args()
    url = database_url()
    before = demo_state(url)
    test_name = "smartdoc_tv3_test_" + uuid.uuid4().hex
    admin_url = make_conninfo(url, dbname="postgres", connect_timeout=5)
    test_url = make_conninfo(url, dbname=test_name, connect_timeout=5)
    created = False
    result = None
    with psycopg.connect(admin_url, autocommit=True) as admin:
        try:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_name)))
            created = True
            print("Created a separate disposable test database.", flush=True)
            with tempfile.TemporaryDirectory(prefix="smartdoc_tv3_db_") as folder:
                env = dict(os.environ, DATABASE_URL=test_url, STORAGE_ROOT=folder, PYTHONUTF8="1",
                           SMARTDOC_ISOLATED_TEST_DB=test_name)
                initialized = subprocess.run([sys.executable, "-m", "scripts.init_db"],
                                             cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
                if initialized.returncode:
                    raise RuntimeError("Could not initialize the disposable test schema.")
                targets = [] if args.all_tests else [
                    "tests/test_ingestion_integration.py", "tests/test_recovery.py", "tests/test_tv3_upload_database.py"]
                result = subprocess.run([
                    sys.executable, "-m", "pytest", "-q", "--tb=short", *targets,
                ], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
                print(result.stdout, flush=True)
        finally:
            if created:
                # Guard the exact target; no user database name is interpolated.
                if (not test_name.startswith("smartdoc_tv3_test_") or len(test_name) != 50
                        or make_conninfo(url) == test_url):
                    raise RuntimeError("Disposable database target failed safety checks.")
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(test_name)))
    after = demo_state(url)
    if before != after:
        raise RuntimeError("Demo database changed during testing; inspect external writers.")
    report = {"test_scope": "separate newly created disposable PostgreSQL database and temporary storage",
              "suite": "all" if args.all_tests else "database integration",
              "returncode": result.returncode, "pytest_output": result.stdout,
              "demo_before": before, "demo_after": after, "test_database_removed": True}
    Path(PROJECT_ROOT / "reports/tv3_database_tests.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print("Demo corpus unchanged; disposable database removed.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
