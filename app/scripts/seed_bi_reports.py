from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.bi_registry import seed_bi_reports


def main() -> None:
    db = SessionLocal()
    try:
        rows = seed_bi_reports(db)
        print("seed_bi_reports complete")
        for row in rows:
            print(
                f"report_key={row.report_key} workspace_id={row.workspace_id} "
                f"report_id={row.report_id} dataset_id={row.dataset_id} enabled={row.is_enabled}"
            )
    except SQLAlchemyError as exc:
        db.rollback()
        raise RuntimeError("Unable to seed bi_reports. Run migrations first (alembic upgrade head).") from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
