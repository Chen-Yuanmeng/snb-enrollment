from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .core.datetime_utils import utcnow_naive
from .database import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    gender: Mapped[int | None] = mapped_column(nullable=True)
    birth_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    school: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentHistory(Base):
    __tablename__ = "students_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    phone_suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    grade: Mapped[str] = mapped_column(String(50), nullable=False)
    class_subjects: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    class_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    mode_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    base_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    final_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    discount_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    non_price_benefits: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    pricing_formula: Mapped[str] = mapped_column(Text, nullable=False)
    pricing_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    quote_valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    quote_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    operator_name: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.id"), nullable=False, index=True
    )
    recalculated_enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey("enrollments.id"), nullable=True
    )
    refund_class_subjects: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    old_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    new_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    refund_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    auto_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_operator_name: Mapped[str] = mapped_column(String(50), nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    operator_name: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operator_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    request_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)


class MessageTask(Base):
    __tablename__ = "message_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    webhook_url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    remote_msg_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_chain: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, index=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
