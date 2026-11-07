"""Storage selection from the DATABASE_URL environment variable."""
from __future__ import annotations

import os

from ..repository import InMemoryRepository, Repository
from .connection import Database, database_from_url, migrate
from .sql_repository import SqlRepository

__all__ = ["Database", "SqlRepository", "database_from_url", "make_repository", "migrate"]


def make_repository(url: str | None = None, *, auto_migrate: bool = True) -> Repository:
    """SQL repository when DATABASE_URL is set, otherwise in-memory."""
    url = url if url is not None else os.environ.get("DATABASE_URL", "")
    if not url:
        return InMemoryRepository()
    db = database_from_url(url)
    if auto_migrate:
        migrate(db)
    return SqlRepository(db)
