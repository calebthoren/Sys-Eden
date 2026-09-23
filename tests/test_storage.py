import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from sys_eden.storage import Database, StorageError


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
