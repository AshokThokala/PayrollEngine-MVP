"""Shared fixtures: run the service tests against every storage backend.

- memory   : always
- sqlite   : always (temporary file)
- postgres : only when TEST_DATABASE_URL is set. The database is WIPED
             (schema "public" dropped) — point it at a throwaway test database.
"""
import os

import pytest

from app.db import SqlRepository, database_from_url, migrate
from app.repository import InMemoryRepository

BACKENDS = ["memory", "sqlite", "postgres"]


@pytest.fixture(params=BACKENDS)
def repo(request, tmp_path):
    if request.param == "memory":
        return InMemoryRepository()
    if request.param == "sqlite":
        db = database_from_url(f"sqlite:///{tmp_path / 'test.db'}")
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL not set")
        pytest.importorskip("psycopg")
        db = database_from_url(url)
        conn = db.connect()
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        conn.close()
    migrate(db)
    return SqlRepository(db)
