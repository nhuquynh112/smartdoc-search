# PostgreSQL with Docker Compose

The shared development database runs in Docker. Python and Streamlit run on the host in a local virtual environment. Each teammate has a separate database; Compose does not synchronize records between machines.

## Prerequisites

- Ubuntu: Docker Engine with the Compose plugin, or Docker Desktop.
- Windows: Docker Desktop with Linux containers enabled.

Official installation guides:

- https://docs.docker.com/engine/install/ubuntu/
- https://docs.docker.com/desktop/setup/install/windows-install/

Check installation:

```bash
docker --version
docker compose version
```

## Configure

Run commands from the repository root. On Ubuntu:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` in your editor. Replace both `CHANGE_ME` occurrences with the same local password. Use letters and digits for the first setup; other characters may require percent-encoding in DATABASE_URL. Do not commit `.env`.

## Start and inspect

```bash
docker compose up -d --wait
docker compose ps
```

Compose publishes the database on `127.0.0.1:5433` to avoid the native PostgreSQL service on port 5432. The image uses PostgreSQL 16 to match the initial Ubuntu installation. The Compose role is a local development bootstrap administrator, not a production least-privilege account.

Open a database session without requiring psql on the host:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

This command works in Bash and PowerShell. In psql:

```sql
SELECT current_database(), current_user;
\q
```

Expected defaults: database `smartdoc`, user `smartdoc_app`.

A healthy status verifies server readiness, not that Python credentials or the project schema have been tested. Run `python -m scripts.init_db` and `python -m scripts.check_db` after installing requirements in the virtual environment; see the root README.

## Stop and resume

```bash
docker compose down
docker compose up -d --wait
```

The named volume retains data when containers are removed with `down`. Do not append `-v` unless deliberately deleting the local database. Changing POSTGRES_DB, POSTGRES_USER or POSTGRES_PASSWORD in `.env` does not modify an already initialized volume; update the existing database explicitly instead.

## Troubleshooting

- Docker daemon unavailable: start Docker Desktop or the Docker service.
- Ubuntu socket permission denied: follow Docker's Linux post-installation guide; avoid making the socket world-writable. A properly configured `sudo docker compose` can also be used consistently on Ubuntu.
- Port 5433 occupied: change POSTGRES_PORT and the port in DATABASE_URL to the same unused value.
- Python authentication failure: verify the password and host port in DATABASE_URL. The host connects to localhost:5433, not localhost:5432.
- Container startup failure: inspect `docker compose logs --tail=50 db`; redact credentials before sharing logs.

## Current validation status

Container startup and a container-local database/user query have been verified on Ubuntu. Host Python authentication and schema initialization are also verified on Ubuntu. Windows execution remains to be verified.
