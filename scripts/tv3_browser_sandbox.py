"""Run manual browser acceptance in a disposable PostgreSQL container.

Uses the already installed postgres:16 image; never downloads an image. The
demo database, .env, storage and UI index are untouched. Ctrl+C cleans up only
the container created by this process and its temporary test files.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import psycopg
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]


def prepare_reports_directory(root):
    reports = Path(root).resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


def check_ui_port(port):
    """Bind and listen locally before creating any disposable resources."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("UI port must be an integer from 1 to 65535.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
            probe.listen(1)
        except OSError as exc:
            raise RuntimeError("UI port is already occupied or unavailable. Choose a separate --port; do not use the demo app port.") from exc


def wait_app(process, health_url, *, timeout=30, open_url=None, clock=time.monotonic,
             sleep=time.sleep):
    """Require the owned process and its unique health route to be ready.

    Port preflight alone has a close/start race. A random base URL path plus
    Streamlit's exact health body prevents an existing app on the same port
    from being mistaken for this sandbox after such a race.
    """
    open_url = open_url or urlopen
    deadline = clock() + timeout
    while clock() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned Streamlit process exited before becoming ready. Check the private sandbox log or choose a separate UI port.")
        ready = False
        try:
            with open_url(health_url, timeout=1) as response:
                ready = response.status == 200 and response.read(64).strip() == b"ok"
        except (OSError, URLError):
            pass
        if ready:
            if process.poll() is not None:
                raise RuntimeError("Owned Streamlit process stopped during its readiness check.")
            return
        sleep(0.1)
    raise RuntimeError("Owned Streamlit did not become ready in time. No isolated UI URL has been published; check the private sandbox log.")


def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def docker(*arguments, env=None):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True,
                            env=env, timeout=90)
    if result.returncode:
        raise RuntimeError(f"Docker command failed: {arguments[0]}. Check Docker Desktop.")
    return result.stdout.strip()


def wait_database(url):
    for _ in range(60):
        try:
            with psycopg.connect(url, connect_timeout=1) as conn:
                conn.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            time.sleep(0.25)
    raise RuntimeError("The isolated PostgreSQL server did not become ready.")


def make_fixtures(folder):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    folder.mkdir()
    (folder / "xe_dien.txt").write_text(
        "Xe điện và năng lượng xanh\nÔ tô điện sử dụng pin và trạm sạc. "
        "Năng lượng tái tạo giúp giảm khí thải trong giao thông Việt Nam.", encoding="utf-8")
    (folder / "rong.txt").write_bytes(b"")
    (folder / "loi.pdf").write_bytes(b"This is an intentionally invalid PDF fixture.")
    blank = PdfWriter()
    blank.add_blank_page(width=400, height=400)
    blank.write(folder / "pdf_khong_text.pdf")
    writer = PdfWriter()
    page = writer.add_blank_page(width=500, height=500)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 14 Tf 30 450 Td (Artificial intelligence technology and computer science.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(folder / "cong_nghe.pdf")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8504)
    parser.add_argument("--database-port", type=int, default=55433)
    args = parser.parse_args()
    check_ui_port(args.port)
    docker("image", "inspect", "postgres:16")
    name = "smartdoc-tv3-qa-" + uuid.uuid4().hex
    token = secrets.token_urlsafe(30)
    url = make_conninfo(host="127.0.0.1", port=args.database_port, user="postgres",
                        password=token, dbname="smartdoc_tv3_qa", connect_timeout=2)
    container_id = None
    server = None
    reports = prepare_reports_directory(ROOT)
    base_path = "tv3-qa-" + uuid.uuid4().hex
    app_url = f"http://127.0.0.1:{args.port}/{base_path}"
    health_url = f"{app_url}/_stcore/health"
    with tempfile.TemporaryDirectory(prefix="tv3_browser_", dir=reports) as temporary:
        folder = Path(temporary).resolve()
        if not folder.is_relative_to((ROOT / "reports").resolve()):
            raise RuntimeError("Invalid sandbox folder.")
        log = (folder / "streamlit.log").open("w", encoding="utf-8")
        try:
            container_id = docker("run", "-d", "--name", name,
                                  "--label", "smartdoc.tv3.disposable=true",
                                  "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=smartdoc_tv3_qa",
                                  "-p", f"127.0.0.1:{args.database_port}:5432", "postgres:16",
                                  env=dict(os.environ, POSTGRES_PASSWORD=token))
            wait_database(url)
            env = dict(os.environ, DATABASE_URL=url, STORAGE_ROOT=str(folder / "storage"),
                       SMARTDOC_INDEX_ROOT=str(folder / "index"), PYTHONUTF8="1")
            subprocess.run([sys.executable, "-m", "scripts.init_db"], cwd=ROOT, env=env,
                           capture_output=True, check=True, timeout=30)
            # The process is solely connected to its newly created server.
            os.environ.update({key: env[key] for key in ("DATABASE_URL", "STORAGE_ROOT", "SMARTDOC_INDEX_ROOT")})
            from smartdoc.ingestion import delete_document, ingest_document, load_corpus_snapshot
            from app.search_service import SearchService
            seed = folder / "seed.txt"
            seed.write_text("Giáo dục Việt Nam\nHọc sinh học tập tại trường và phát triển kiến thức.", encoding="utf-8")
            ingest_document(seed, corpus_name="browser_test", title="Tài liệu giáo dục thử nghiệm")
            service = SearchService()
            if not service.rebuild().get("rebuilt"):
                raise RuntimeError("Could not build the isolated seed index.")
            make_fixtures(folder / "fixtures")

            def start_app():
                check_ui_port(args.port)
                process = subprocess.Popen([
                    sys.executable, "-X", "utf8", "-m", "streamlit", "run", "app/main.py",
                    "--server.address", "127.0.0.1", "--server.port", str(args.port),
                    "--server.baseUrlPath", base_path,
                    "--server.headless", "true", "--browser.gatherUsageStats", "false",
                ], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    wait_app(process, health_url)
                except BaseException:
                    stop_process(process)
                    raise
                return process

            def stop_app():
                stop_process(server)

            server = start_app()
            print(f"Isolated UI: {app_url}", flush=True)
            print(f"Synthetic upload fixtures: {folder / 'fixtures'}", flush=True)
            print("Commands: status | restart_app | restart_db | disconnect | reconnect | delete ID | quit", flush=True)
            for line in sys.stdin:
                command = line.strip()
                if command == "quit":
                    break
                if command == "restart_app":
                    stop_app()
                    server = start_app()
                    print("Isolated Streamlit restarted.", flush=True)
                elif command == "restart_db":
                    docker("restart", name)
                    wait_database(url)
                    print("Isolated PostgreSQL restarted; data volume retained.", flush=True)
                elif command == "disconnect":
                    docker("stop", name)
                    print("Only isolated PostgreSQL stopped.", flush=True)
                elif command == "reconnect":
                    docker("start", name)
                    wait_database(url)
                    print("Only isolated PostgreSQL started.", flush=True)
                elif command.startswith("delete "):
                    doc_id = int(command.split()[1])
                    ids = {row["document_id"] for row in load_corpus_snapshot()["documents"]}
                    if doc_id not in ids:
                        raise ValueError("ID is not in the isolated test corpus.")
                    delete_document(doc_id)
                    print(f"Deleted only test document #{doc_id}.", flush=True)
                if command == "status" or command.startswith("delete "):
                    snapshot = load_corpus_snapshot()
                    print({"ready_ids": [row["document_id"] for row in snapshot["documents"]],
                           "revision": snapshot["corpus_revision"], "index": service.status()["status"]}, flush=True)
        finally:
            if server:
                stop_app()
            log.close()
            if container_id:
                # Never target an existing/demo container: validate the exact ID
                # returned by this process's successful docker run.
                actual_id = docker("inspect", "--format", "{{.Id}}", name)
                if actual_id != container_id or not name.startswith("smartdoc-tv3-qa-"):
                    raise RuntimeError("Container identity changed; refusing cleanup.")
                docker("rm", "-f", "-v", container_id)
                print("Owned test container/volume removed; demo untouched.", flush=True)


if __name__ == "__main__":
    main()
