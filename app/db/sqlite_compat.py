"""
SQLite compatibility for Postgres-specific column types.

The production deployment targets Postgres, but unit tests use SQLite for speed.
These compilation shims allow Base.metadata.create_all() to work on SQLite without
changing the model field types used in Postgres.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type: JSONB, _compiler, **_kw) -> str:
    # SQLite stores JSON as TEXT; SQLAlchemy's JSON type compiles to "JSON".
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(_type: UUID, _compiler, **_kw) -> str:
    # Store UUIDs as 36-char strings in SQLite.
    return "CHAR(36)"

