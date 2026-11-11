"""Database connections and migrations.

DATABASE_URL examples:
  postgresql://payroll:payroll@localhost:5432/payroll   (needs psycopg)
  sqlite:///./payroll.db                                (local tests / demos)
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

SERIAL_PK = {
    "postgres": "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
    "sqlite": "INTEGER PRIMARY KEY AUTOINCREMENT",
}


@dataclass(frozen=True)
class Database:
    dialect: str  # "postgres" | "sqlite"
    connect: Callable[[], Any]  # a new, unpooled connection (migrations, tests)
    pool: Any = None  # psycopg_pool.ConnectionPool for PostgreSQL

    @contextmanager
    def session(self) -> Iterator[Any]:
        """A connection for one unit of work: borrowed from the pool when there is one."""
        if self.pool is not None:
            with self.pool.connection() as conn:
                yield conn
            return
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()


def database_from_url(url: str) -> Database:
    if url.startswith(("postgresql://", "postgres://")):
        import psycopg  # imported lazily so SQLite tests need no driver

        pool = None
        if os.environ.get("DB_POOL_SIZE", "10") != "0":
            from psycopg_pool import ConnectionPool

            # One pool per API worker process; connections are reused across requests.
            pool = ConnectionPool(url, min_size=1, max_size=int(os.environ.get("DB_POOL_SIZE", "10")),
                                  open=True, name="clearpay4u")
        return Database("postgres", lambda: psycopg.connect(url), pool)
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]

        def connect():
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        return Database("sqlite", connect)
    raise ValueError(f"Unsupported DATABASE_URL: {url!r}")


def _migration_files(dialect: str) -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if dialect != "postgres":
        files = [f for f in files if not f.name.endswith(".postgres.sql")]
    return files


def migrate(db: Database) -> list[str]:
    """Apply pending migrations in order. Returns the versions applied."""
    conn = db.connect()
    applied_now: list[str] = []
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY,"
            " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
        cur.execute("SELECT version FROM schema_migrations")
        done = {row[0] for row in cur.fetchall()}
        ph = "%s" if db.dialect == "postgres" else "?"
        for path in _migration_files(db.dialect):
            version = path.name.split(".")[0]
            if version in done:
                continue
            sql = path.read_text().replace("{serial_pk}", SERIAL_PK[db.dialect])
            if db.dialect == "sqlite":
                conn.executescript(sql)
            else:
                cur.execute(sql)
            cur.execute(f"INSERT INTO schema_migrations (version) VALUES ({ph})", (version,))
            conn.commit()
            applied_now.append(version)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return applied_now
