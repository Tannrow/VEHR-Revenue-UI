from __future__ import annotations

import os

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _make_session():
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def test_revenue_era_structured_results_are_immutable_after_finalization() -> None:
    db = _make_session()
    try:
        # Insert minimal parent rows
        org_id = db.execute(
            text(
                "INSERT INTO organizations (name) VALUES (:name) RETURNING id"
            ),
            {"name": "ERA Immutability Org"},
        ).scalar_one()
        db.commit()

        era_file_id = db.execute(
            text(
                "INSERT INTO revenue_era_files "
                "(organization_id, file_name, sha256, storage_ref, status) "
                "VALUES (:org_id, :file_name, :sha256, :storage_ref, :status) RETURNING id"
            ),
            {
                "org_id": org_id,
                "file_name": "era.pdf",
                "sha256": "immutable-era-sha",
                "storage_ref": "s3://era.pdf",
                "status": "structured",
            },
        ).scalar_one()
        db.commit()

        structured_id = db.execute(
            text(
                "INSERT INTO revenue_era_structured_results "
                "(era_file_id, llm, deployment, api_version, prompt_version, structured_json) "
                "VALUES (:era_file_id, :llm, :deployment, :api_version, :prompt_version, :json::jsonb) "
                "RETURNING id"
            ),
            {
                "era_file_id": era_file_id,
                "llm": "gpt",
                "deployment": "deploy",
                "api_version": "v1",
                "prompt_version": "p1",
                "json": "{}",
            },
        ).scalar_one()
        db.commit()

        # Finalize the row
        db.execute(
            text(
                "UPDATE revenue_era_structured_results SET finalized_at = NOW() WHERE id = :id"
            ),
            {"id": structured_id},
        )
        db.commit()

        # Assert UPDATE is blocked
        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
            db.execute(
                text(
                    "UPDATE revenue_era_structured_results SET llm = :llm WHERE id = :id"
                ),
                {"llm": "blocked", "id": structured_id},
            )
            db.commit()
        assert exc_info.value.orig.pgcode == "45000"
        db.rollback()

        # Assert DELETE is blocked
        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
            db.execute(
                text("DELETE FROM revenue_era_structured_results WHERE id = :id"),
                {"id": structured_id},
            )
            db.commit()
        assert exc_info.value.orig.pgcode == "45000"
        db.rollback()

    finally:
        db.rollback()
        db.close()
