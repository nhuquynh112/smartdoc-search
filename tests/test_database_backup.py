"""Backup naming/concurrency and restore checks without invoking Docker."""
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import backup_database, restore_database


def run_backup(monkeypatch, path):
    monkeypatch.setattr(sys, 'argv', ['backup_database', '--output', str(path)])
    backup_database.main()


def fake_docker(payload=b'archive fixture'):
    def run(command, **kwargs):
        if hasattr(kwargs.get('stdout'), 'write'):
            kwargs['stdout'].write(payload)
        elif 'stdin' in kwargs:
            assert kwargs['stdin'].read() == payload
        return SimpleNamespace(stdout='0\n')
    return run


def test_existing_temporary_file_is_never_deleted(tmp_path, monkeypatch):
    output = tmp_path / 'team.dump'
    temporary = tmp_path / 'team.dump.tmp'
    temporary.write_bytes(b'owned by another backup')
    docker = Mock()
    monkeypatch.setattr(backup_database.subprocess, 'run', docker)
    with pytest.raises((FileExistsError, SystemExit)):
        run_backup(monkeypatch, output)
    assert temporary.read_bytes() == b'owned by another backup'
    docker.assert_not_called()


def test_concurrent_backup_cannot_remove_first_writers_file(tmp_path, monkeypatch):
    output = tmp_path / 'team.dump'
    nested = False

    def docker(command, **kwargs):
        nonlocal nested
        if hasattr(kwargs.get('stdout'), 'write'):
            assert not nested
            nested = True
            kwargs['stdout'].write(b'archive fixture')
            kwargs['stdout'].flush()
            with pytest.raises((FileExistsError, SystemExit)):
                run_backup(monkeypatch, output)
            assert (tmp_path / 'team.dump.tmp').exists()
        return SimpleNamespace(stdout='0\n')

    monkeypatch.setattr(backup_database.subprocess, 'run', docker)
    run_backup(monkeypatch, output)
    assert output.read_bytes() == b'archive fixture'
    assert not (tmp_path / 'team.dump.tmp').exists()


def test_different_extensions_keep_independent_manifests(tmp_path, monkeypatch):
    for name, payload in [('snapshot.dump', b'first'), ('snapshot.backup', b'second')]:
        monkeypatch.setattr(backup_database.subprocess, 'run', fake_docker(payload))
        run_backup(monkeypatch, tmp_path / name)
    for name, payload in [('snapshot.dump', b'first'), ('snapshot.backup', b'second')]:
        manifest = json.loads((tmp_path / (name + '.manifest.json')).read_text())
        assert manifest['sha256'] == hashlib.sha256(payload).hexdigest()


def test_existing_manifest_is_not_overwritten(tmp_path, monkeypatch):
    output = tmp_path / 'team.dump'
    manifest = tmp_path / 'team.dump.manifest.json'
    manifest.write_text('existing evidence')
    docker = Mock()
    monkeypatch.setattr(backup_database.subprocess, 'run', docker)
    with pytest.raises(SystemExit):
        run_backup(monkeypatch, output)
    assert manifest.read_text() == 'existing evidence'
    assert not output.exists()
    docker.assert_not_called()


def test_failed_dump_cleans_only_its_temporary_file(tmp_path, monkeypatch):
    output = tmp_path / 'team.dump'
    monkeypatch.setattr(backup_database.subprocess, 'run', Mock(
        side_effect=subprocess.CalledProcessError(1, 'pg_dump')))
    with pytest.raises(subprocess.CalledProcessError):
        run_backup(monkeypatch, output)
    assert not output.exists()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('legacy', [False, True])
def test_restore_reads_new_and_legacy_manifest(tmp_path, monkeypatch, legacy):
    archive = tmp_path / 'team.dump'
    archive.write_bytes(b'archive fixture')
    path = archive.with_suffix('.manifest.json') if legacy else tmp_path / 'team.dump.manifest.json'
    path.write_text(json.dumps({'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))
    docker = Mock(side_effect=fake_docker())
    monkeypatch.setattr(restore_database.subprocess, 'run', docker)
    monkeypatch.setattr(sys, 'argv', ['restore_database', str(archive)])
    restore_database.main()
    assert docker.call_count == 2


def test_restore_does_not_fall_back_when_new_manifest_checksum_is_wrong(tmp_path, monkeypatch):
    archive = tmp_path / 'team.dump'
    archive.write_bytes(b'archive fixture')
    archive.with_suffix('.manifest.json').write_text(json.dumps({
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))
    (tmp_path / 'team.dump.manifest.json').write_text(json.dumps({'sha256': 'wrong'}))
    docker = Mock()
    monkeypatch.setattr(restore_database.subprocess, 'run', docker)
    monkeypatch.setattr(sys, 'argv', ['restore_database', str(archive)])
    with pytest.raises(SystemExit):
        restore_database.main()
    docker.assert_not_called()
