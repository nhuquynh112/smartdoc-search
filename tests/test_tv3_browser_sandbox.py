"""Sandbox startup safety without Docker, PostgreSQL or a real app process."""
import socket
import subprocess

import pytest

from scripts.tv3_browser_sandbox import check_ui_port, prepare_reports_directory, stop_process, wait_app


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, interval):
        self.value += interval


class Process:
    def __init__(self, polls=None, timeout=False):
        self.polls = list(polls or [None])
        self.timeout = timeout
        self.events = []

    def poll(self):
        value = self.polls[0]
        if len(self.polls) > 1:
            self.polls.pop(0)
        return value

    def terminate(self):
        self.events.append("terminate")

    def kill(self):
        self.events.append("kill")

    def wait(self, timeout):
        self.events.append(("wait", timeout))
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired("synthetic-streamlit", timeout)


class Response:
    def __init__(self, body=b"ok", status=200):
        self.body, self.status = body, status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, limit):
        return self.body[:limit]


def test_fresh_checkout_reports_directory_is_created(tmp_path):
    root = tmp_path / "fresh-repository"
    reports = prepare_reports_directory(root)
    assert reports == root.resolve() / "reports"
    assert reports.is_dir()
    marker = reports / "keep.txt"
    marker.write_text("Existing report", encoding="utf-8")
    assert prepare_reports_directory(root) == reports
    assert marker.read_text(encoding="utf-8") == "Existing report"


def test_occupied_ui_port_is_rejected_without_stopping_its_owner():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
        owner.bind(("127.0.0.1", 0))
        owner.listen(1)
        port = owner.getsockname()[1]
        with pytest.raises(RuntimeError, match="already occupied"):
            check_ui_port(port)
        # The original listener remains usable after the failed preflight.
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            connection, _address = owner.accept()
            connection.close()


@pytest.mark.parametrize("port", [0, -1, 65536, True, "8504"])
def test_invalid_ports_are_rejected_before_any_resource_start(port):
    with pytest.raises(ValueError, match="UI port"):
        check_ui_port(port)


def test_early_child_death_never_uses_health_of_an_existing_app():
    process = Process([1])

    def wrong_app(_url, **_kwargs):
        pytest.fail("Readiness must check the owned process before requesting HTTP.")

    with pytest.raises(RuntimeError, match="exited before"):
        wait_app(process, "http://127.0.0.1:8504/random-sandbox/_stcore/health", open_url=wrong_app)


def test_health_at_unique_path_requires_exact_streamlit_health_body():
    clock = Clock()
    requested = []

    def existing_app_fallback(url, **_kwargs):
        requested.append(url)
        return Response(b"<html>Another running app</html>")

    health = "http://127.0.0.1:8504/random-sandbox/_stcore/health"
    with pytest.raises(RuntimeError, match="No isolated UI URL"):
        wait_app(Process(), health, timeout=0.3, open_url=existing_app_fallback,
                 clock=clock, sleep=clock.sleep)
    assert requested and set(requested) == {health}


def test_child_death_during_health_check_is_not_reported_ready():
    with pytest.raises(RuntimeError, match="stopped during"):
        wait_app(Process([None, 1]), "http://127.0.0.1:8504/random/_stcore/health",
                 open_url=lambda *_args, **_kwargs: Response())


def test_owned_process_and_unique_health_route_become_ready():
    clock = Clock()
    calls = []

    def warming_up(url, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("Synthetic connection refused")
        return Response(b"ok")

    health = "http://127.0.0.1:8504/random-sandbox/_stcore/health"
    wait_app(Process(), health, timeout=1, open_url=warming_up, clock=clock, sleep=clock.sleep)
    assert calls == [health, health]


def test_stop_process_only_terminates_the_owned_process_and_escalates_if_needed():
    process = Process(timeout=True)
    stop_process(process)
    assert process.events == ["terminate", ("wait", 10), "kill", ("wait", 5)]
    already_stopped = Process([0])
    stop_process(already_stopped)
    assert already_stopped.events == []
