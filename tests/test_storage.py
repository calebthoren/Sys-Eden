import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import text

import sys_eden.storage as storage_module
from sys_eden.storage import Database, StorageError


def _sqlite_error(code: int) -> sqlite3.OperationalError:
    error = sqlite3.OperationalError("generated SQLite failure")
    error.sqlite_errorcode = code
    return error


def test_windows_wal_initialization_retries_only_the_transient_truncate_error(monkeypatch):
    cursor = Mock(spec=sqlite3.Cursor)
    cursor.execute.side_effect = [_sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE), None]
    sleep = Mock()
    monkeypatch.setattr(storage_module, "_WINDOWS", True)
    monkeypatch.setattr(storage_module.time, "sleep", sleep)
    storage_module._enable_wal(cursor)
    assert cursor.execute.call_count == 2
    sleep.assert_called_once_with(0.05)


@pytest.mark.parametrize("windows, code", [
    (True, sqlite3.SQLITE_IOERR_WRITE),
    (True, sqlite3.SQLITE_CORRUPT),
    (False, sqlite3.SQLITE_IOERR_TRUNCATE),
])
def test_other_storage_failures_are_not_retried(monkeypatch, windows, code):
    cursor = Mock(spec=sqlite3.Cursor)
    error = _sqlite_error(code)
    cursor.execute.side_effect = error
    sleep = Mock()
    monkeypatch.setattr(storage_module, "_WINDOWS", windows)
    monkeypatch.setattr(storage_module.time, "sleep", sleep)
    with pytest.raises(sqlite3.OperationalError) as caught:
        storage_module._enable_wal(cursor)
    assert caught.value is error
    assert cursor.execute.call_count == 1
    sleep.assert_not_called()


def test_windows_wal_recovery_retry_is_bounded(monkeypatch):
    cursor = Mock(spec=sqlite3.Cursor)
    error = _sqlite_error(sqlite3.SQLITE_IOERR_TRUNCATE)
    cursor.execute.side_effect = error
    monkeypatch.setattr(storage_module, "_WINDOWS", True)
    monkeypatch.setattr(storage_module.time, "monotonic", Mock(side_effect=[0, 0, 3]))
    monkeypatch.setattr(storage_module.time, "sleep", Mock())
    with pytest.raises(sqlite3.OperationalError) as caught:
        storage_module._enable_wal(cursor)
    assert caught.value is error
    assert cursor.execute.call_count == 2


def test_baseline_is_repeatable_and_sqlite_settings_apply(tmp_path: Path):
    database = Database(tmp_path / "data" / "eden.db")
    try:
        database.initialize()
        database.initialize()
        assert database.healthy()
        with database.session() as session:
            assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert session.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
            assert session.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert database.path.with_suffix(".pre-unversioned.db").exists()
    finally:
        database.close()


def test_failed_session_rolls_back_and_restart_preserves_schema(tmp_path: Path):
    path = tmp_path / "eden.db"
    database = Database(path)
    try:
        database.initialize()
        with pytest.raises(RuntimeError), database.session() as session:
            session.execute(text("UPDATE alembic_version SET version_num = 'broken'"))
            raise RuntimeError("synthetic failure")
        assert database.healthy()
    finally:
        database.close()
    reopened = Database(path)
    try:
        reopened.initialize()
        assert reopened.healthy()
    finally:
        reopened.close()


def test_unknown_revision_preserved(tmp_path: Path):
    path = tmp_path / "eden.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('future')")
    database = Database(path)
    try:
        with pytest.raises(StorageError, match="Unsupported"):
            database.initialize()
        with database.session() as session:
            assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "future"
            )
    finally:
        database.close()


def test_known_older_revision_is_backed_up_and_upgraded(tmp_path: Path):
    path = tmp_path / "eden.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001')")
    database = Database(path)
    try:
        database.initialize()
        assert database.healthy()
        assert path.with_suffix(".pre-0001.db").exists()
        with database.session() as session:
            assert session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='reports'")
            ).scalar_one() == "reports"
    finally:
        database.close()
