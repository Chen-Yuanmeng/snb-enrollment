from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import config


engine = create_engine(config.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def ensure_runtime_schema_compatibility() -> None:
    """Apply additive schema patches for already-deployed databases.

    Base.metadata.create_all only creates missing tables and won't add new columns
    to existing tables. This keeps production instances forward-compatible.
    """

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "enrollments" in table_names:
            enrollment_columns = {col["name"] for col in inspector.get_columns("enrollments")}
            if "chain_root_enrollment_id" not in enrollment_columns:
                conn.execute(text("ALTER TABLE enrollments ADD COLUMN chain_root_enrollment_id BIGINT"))
            if "previous_enrollment_id" not in enrollment_columns:
                conn.execute(text("ALTER TABLE enrollments ADD COLUMN previous_enrollment_id BIGINT"))
            conn.execute(
                text(
                    "UPDATE enrollments "
                    "SET chain_root_enrollment_id = id "
                    "WHERE chain_root_enrollment_id IS NULL"
                )
            )

        if "refunds" in table_names:
            refund_columns = {col["name"] for col in inspector.get_columns("refunds")}
            if "task_type" not in refund_columns:
                conn.execute(
                    text(
                        "ALTER TABLE refunds "
                        "ADD COLUMN task_type VARCHAR(20) NOT NULL DEFAULT 'decrease'"
                    )
                )
            if "status" not in refund_columns:
                conn.execute(
                    text(
                        "ALTER TABLE refunds "
                        "ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"
                    )
                )
            if "confirmed_at" not in refund_columns:
                conn.execute(text("ALTER TABLE refunds ADD COLUMN confirmed_at TIMESTAMP NULL"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
