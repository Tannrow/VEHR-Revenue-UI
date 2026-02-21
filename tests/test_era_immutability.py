from __future__ import annotations

import os
import json
from contextlib import contextmanager
from datetime import datetime
import uuid

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@contextmanager
def _make_session():
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url, future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _sqlstate(exc: sqlalchemy.exc.DBAPIError) -> str | None:
    orig = exc.orig
    # psycopg v3
    if hasattr(orig, "sqlstate"):
        return getattr(orig, "sqlstate", None)
    # psycopg2
    if hasattr(orig, "pgcode"):
        return getattr(orig, "pgcode", None)
    return None


def test_revenue_era_structured_results_are_immutable_after_finalization() -> None:
    with _make_session() as db:
        org_id = str(uuid.uuid4())
        era_file_id = str(uuid.uuid4())
        structured_id = str(uuid.uuid4())

        db.execute(
            text(
                "INSERT INTO organizations (id, name, created_at) "
                "VALUES (:id, :name, :created_at)"
            ),
            {"id": org_id, "name": "ERA Immutability Org", "created_at": datetime.utcnow()},
        )

        db.execute(
            text(
                "INSERT INTO revenue_era_files "
                "(id, organization_id, file_name, sha256, storage_ref, status) "
                "VALUES (:id, :org_id, :file_name, :sha256, :storage_ref, :status)"
            ),
            {
                "id": era_file_id,
                "org_id": org_id,
                "file_name": "era.pdf",
                "sha256": "immutable-era-sha",
                "storage_ref": "s3://era.pdf",
                "status": "structured",
            },
        )

        db.execute(
            text(
                "INSERT INTO revenue_era_structured_results "
                "(id, era_file_id, llm, deployment, api_version, prompt_version, structured_json) "
                "VALUES (:id, :era_file_id, :llm, :deployment, :api_version, :prompt_version, :structured_json)"
            ),
            {
                "id": structured_id,
                "era_file_id": era_file_id,
                "llm": "gpt",
                "deployment": "deploy",
                "api_version": "v1",
                "prompt_version": "p1",
                "structured_json": json.dumps({}),
            },
        )

        db.execute(
            text(
                "UPDATE revenue_era_structured_results "
                "SET finalized_at = NOW() WHERE id = :id"
            ),
            {"id": structured_id},
        )

        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE revenue_era_structured_results "
                        "SET llm = :llm WHERE id = :id"
                    ),
                    {"llm": "blocked", "id": structured_id},
                )
        assert _sqlstate(exc_info.value) == "45000"

        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
            with db.begin_nested():
                db.execute(
                    text("DELETE FROM revenue_era_structured_results WHERE id = :id"),
                    {"id": structured_id},
                )
        assert _sqlstate(exc_info.value) == "45000"
