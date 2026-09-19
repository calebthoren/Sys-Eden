"""SQLite lifecycle and transactional sessions for local repositories."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

BASELINE_REVISION = "0001"


class StorageError(Exception):
    """Local persistence could not be initialized or accessed."""


def _configure_connection(connection: sqlite3.Connection, _: object) -> None:
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()
        connection.autocommit = previous_autocommit


class Database:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.engine: Engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            connect_args={"autocommit": False},
        )
        event.listen(self.engine, "connect", _configure_connection)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        """Apply the packaged baseline; preserve unknown schemas without modification."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
            if revision == BASELINE_REVISION:
                return
            if revision is not None:
                raise StorageError("Unsupported database schema revision")
        # Use SQLite's backup API so existing WAL contents are included.
        backup = self.path.with_suffix(".pre-migration.db")
        if backup.exists():
            raise StorageError("A pre-migration backup already exists; preserve it for review")
        with sqlite3.connect(self.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise StorageError("Database backup verification failed")
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Commit successful repository work and roll back failed work."""
        with self.sessions.begin() as session:
            yield session

    def healthy(self) -> bool:
        with self.session() as session:
            return session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                BASELINE_REVISION
            )

    def close(self) -> None:
        self.engine.dispose()
