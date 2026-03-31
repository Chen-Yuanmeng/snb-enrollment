from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Enrollment, Student
from app.schemas import AccommodationCreateRequest, AccommodationStatusUpdateRequest
from app.services import accommodation_service

from app.database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def _seed_enrollment(db):
    student = Student(name="张三", phone="13800000001")
    db.add(student)
    db.flush()

    enrollment = Enrollment(
        student_id=student.id,
        grade="新高二暑",
        class_subjects=["英才数学"],
        class_mode="线下",
        mode_details=None,
        base_price=1000,
        discount_total=100,
        final_price=900,
        discount_info={"早鸟": 100},
        non_price_benefits={"notes": []},
        pricing_formula="base-discount",
        pricing_snapshot={"version": 1},
        quote_valid_until=_utcnow_naive(),
        quote_fingerprint="fp-1",
        status="quoted",
        valid=True,
        operator_name="测试",
        source="测试",
    )
    db.add(enrollment)
    db.commit()
    return enrollment.id


def test_create_accommodation_with_default_price():
    db = _make_session()
    try:
        related_enrollment_id = _seed_enrollment(db)
        payload = AccommodationCreateRequest(
            operator_name="测试",
            source="测试",
            related_enrollment_id=related_enrollment_id,
            hotel="酒店1",
            room_type="标间拼房",
            duration_days=31,
            gender="男",
            note="测试备注",
        )
        result = accommodation_service.create_accommodation(db, payload)
        assert result["status"] == "generated"
        assert result["nightly_price"] == 120.0
        assert result["total_price"] == 3720.0
        assert "【住宿报价】" in result["quote_text"]
    finally:
        db.close()


def test_create_other_room_type_requires_custom_fields():
    db = _make_session()
    try:
        related_enrollment_id = _seed_enrollment(db)
        payload = AccommodationCreateRequest(
            operator_name="测试",
            source="测试",
            related_enrollment_id=related_enrollment_id,
            hotel="酒店2",
            room_type="其他房型",
            duration_days=27,
            gender="女",
            other_room_type_name="行政套房",
            nightly_price=350,
        )
        result = accommodation_service.create_accommodation(db, payload)
        assert result["status"] == "generated"
        assert result["nightly_price"] == 350.0
        assert result["total_price"] == 9450.0
    finally:
        db.close()


def test_accommodation_status_flow():
    db = _make_session()
    try:
        related_enrollment_id = _seed_enrollment(db)
        create_payload = AccommodationCreateRequest(
            operator_name="测试",
            source="测试",
            related_enrollment_id=related_enrollment_id,
            hotel="酒店1",
            room_type="标间拼房",
            duration_days=31,
            gender="男",
        )
        created = accommodation_service.create_accommodation(db, create_payload)
        accommodation_id = created["accommodation_id"]

        confirmed = accommodation_service.update_accommodation_status(
            db,
            accommodation_id,
            AccommodationStatusUpdateRequest(operator_name="测试", source="测试", status="confirmed"),
        )
        assert confirmed["status"] == "confirmed"

        cancelled = accommodation_service.update_accommodation_status(
            db,
            accommodation_id,
            AccommodationStatusUpdateRequest(operator_name="测试", source="测试", status="cancelled"),
        )
        assert cancelled["status"] == "cancelled"

        with pytest.raises(HTTPException) as exc:
            accommodation_service.update_accommodation_status(
                db,
                accommodation_id,
                AccommodationStatusUpdateRequest(
                    operator_name="测试", source="测试", status="cancelled"
                ),
            )
        assert exc.value.detail["code"] == 40005
    finally:
        db.close()
