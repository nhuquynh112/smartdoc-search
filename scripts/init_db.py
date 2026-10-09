"""Run from the repository root: python -m scripts.init_db."""
from smartdoc.config import PROJECT_ROOT
from smartdoc.db import connect

def main():
    schema = (PROJECT_ROOT / 'database' / 'schema.sql').read_text(encoding='utf-8')
    with connect() as conn:
        conn.execute(schema)
        for migration in sorted((PROJECT_ROOT / "database" / "migrations").glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
    print('Database schema initialized successfully.')

if __name__ == '__main__':
    main()
