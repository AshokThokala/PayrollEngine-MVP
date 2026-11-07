"""Command line: python -m app.db migrate"""
import os
import sys

from .connection import database_from_url, migrate


def main(argv: list[str]) -> int:
    if argv[:1] != ["migrate"]:
        print("usage: python -m app.db migrate   (uses DATABASE_URL)")
        return 2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1
    applied = migrate(database_from_url(url))
    print("Applied: " + ", ".join(applied) if applied else "Database is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
