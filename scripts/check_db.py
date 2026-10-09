"""Verify connectivity and schema without displaying connection credentials."""
from smartdoc.db import connect

def main():
    with connect() as conn:
        server = conn.execute('SELECT current_database() AS name').fetchone()
        state = conn.execute('SELECT revision FROM corpus_state WHERE singleton').fetchone()
        count = conn.execute("SELECT count(*) AS count FROM documents WHERE ingest_status = 'ready'").fetchone()
    print(f"Connected to database: {server['name']}")
    print(f"Corpus revision: {state['revision']}; ready documents: {count['count']}")

if __name__ == '__main__':
    main()
