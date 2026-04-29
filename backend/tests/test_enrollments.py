from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from app.main import list_enrollments
from app.models import Enrollment, Student
from app.schemas import EnrollmentCancelRequest, PayRequest
from app.services.enrollment_service import cancel_enrollment, get_enrollment_stats, pay_enrollment
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def _seed_enrollments(db):
    students = [
        Student(name="张三", phone="13800000001"),
        Student(name="李四", phone="13800000002"),
        Student(name="王五", phone="13800000003"),
    ]
    db.add_all(students)
    db.flush()

    enrollments = [
        Enrollment(
            student_id=students[0].id,
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
            status="unconfirmed",
            valid=True,
            operator_name="测试",
            source="测试",
            chain_root_enrollment_id=None,
            previous_enrollment_id=None,
        ),
        Enrollment(
            student_id=students[1].id,
            grade="新高二暑",
            class_subjects=["英才物理"],
            class_mode="线下",
            mode_details=None,
            base_price=1200,
            discount_total=0,
            final_price=1200,
            discount_info={},
            non_price_benefits={"notes": []},
            pricing_formula="base",
            pricing_snapshot={"version": 1},
            quote_valid_until=_utcnow_naive(),
            quote_fingerprint="fp-2",
            status="confirmed",
            valid=True,
            operator_name="测试",
            source="测试",
            chain_root_enrollment_id=None,
            previous_enrollment_id=None,
        ),
        Enrollment(
            student_id=students[2].id,
            grade="新高三暑",
            class_subjects=["英才化学"],
            class_mode="线上",
            mode_details=None,
            base_price=1300,
            discount_total=50,
            final_price=1250,
            discount_info={"活动": 50},
            non_price_benefits={"notes": []},
            pricing_formula="base-discount",
            pricing_snapshot={"version": 1},
            quote_valid_until=_utcnow_naive(),
            quote_fingerprint="fp-3",
            status="unconfirmed",
            valid=True,
            operator_name="测试",
            source="测试",
            chain_root_enrollment_id=None,
            previous_enrollment_id=None,
        ),
    ]
    db.add_all(enrollments)
    db.flush()
    for row in enrollments:
        row.chain_root_enrollment_id = row.id
    db.commit()


def test_enrollments_pagination_and_total():
    db = _make_session()
    try:
        _seed_enrollments(db)
        result = list_enrollments(page=1, page_size=2, db=db)
        assert result.total == 3
        assert result.page == 1
        assert result.page_size == 2
        assert len(result.data) == 2
        assert result.data[0]["id"] > result.data[1]["id"]

        page2 = list_enrollments(page=2, page_size=2, db=db)
        assert page2.total == 3
        assert page2.page == 2
        assert len(page2.data) == 1
    finally:
        db.close()


def test_enrollments_filter_and_limit_compatibility():
    db = _make_session()
    try:
        _seed_enrollments(db)
        result = list_enrollments(status="unconfirmed", page=1, page_size=20, db=db)
        assert result.total == 2
        assert len(result.data) == 2

        keyword_result = list_enrollments(keyword="李四", page=1, page_size=20, db=db)
        assert keyword_result.total == 1
        assert len(keyword_result.data) == 1
        assert keyword_result.data[0]["student_name"] == "李四"

        compat = list_enrollments(page=4, page_size=1, limit=2, db=db)
        assert compat.page == 1
        assert compat.page_size == 2
        assert len(compat.data) == 2
    finally:
        db.close()


def test_enrollments_default_to_latest_chain_node_only():
    db = _make_session()
    try:
        _seed_enrollments(db)
        old = db.query(Enrollment).filter(Enrollment.student_id == 1).first()
        assert old is not None
        old.status = "pending_adjustment"

        new_row = Enrollment(
            student_id=old.student_id,
            grade=old.grade,
            class_subjects=old.class_subjects,
            class_mode=old.class_mode,
            mode_details=old.mode_details,
            base_price=old.base_price,
            discount_total=old.discount_total,
            final_price=old.final_price,
            discount_info=old.discount_info,
            non_price_benefits=old.non_price_benefits,
            pricing_formula=old.pricing_formula,
            pricing_snapshot=old.pricing_snapshot,
            quote_valid_until=old.quote_valid_until,
            quote_fingerprint="fp-new",
            status="unconfirmed",
            valid=True,
            operator_name="测试",
            source="测试",
            chain_root_enrollment_id=old.chain_root_enrollment_id,
            previous_enrollment_id=old.id,
        )
        db.add(new_row)
        db.commit()

        latest = list_enrollments(page=1, page_size=20, db=db)
        assert all(item["id"] != old.id for item in latest.data)
        assert any(item["id"] == new_row.id for item in latest.data)

        with_history = list_enrollments(page=1, page_size=20, latest_only=False, db=db)
        ids = [item["id"] for item in with_history.data]
        assert old.id in ids
        assert new_row.id in ids
    finally:
        db.close()


def test_pay_enrollment_records_paid_at_in_utc():
    db = _make_session()
    try:
        _seed_enrollments(db)
        row = db.query(Enrollment).filter(Enrollment.status == "unconfirmed").order_by(Enrollment.id.asc()).first()
        assert row is not None

        result = pay_enrollment(
            db,
            row.id,
            PayRequest(operator_name="测试", source="测试", paid_at="04.29 1530", note="手动确认"),
        )
        db.refresh(row)

        assert result["status"] == "confirmed"
        assert row.status == "confirmed"
        assert row.paid_at == datetime(2026, 4, 29, 7, 30)
        assert row.note == "手动确认"
    finally:
        db.close()


def test_pay_enrollment_rejects_invalid_paid_at():
    db = _make_session()
    try:
        _seed_enrollments(db)
        row = db.query(Enrollment).filter(Enrollment.status == "unconfirmed").order_by(Enrollment.id.asc()).first()
        assert row is not None

        with pytest.raises(HTTPException) as exc:
            pay_enrollment(
                db,
                row.id,
                PayRequest(operator_name="测试", source="测试", paid_at="13.40 2561"),
            )

        assert exc.value.status_code == 400
        assert exc.value.detail["message"] == "输入的日期时间无效"
    finally:
        db.close()


def test_cancel_enrollment_keeps_row_listed():
    db = _make_session()
    try:
        _seed_enrollments(db)
        row = db.query(Enrollment).filter(Enrollment.status == "unconfirmed").order_by(Enrollment.id.asc()).first()
        assert row is not None

        result = cancel_enrollment(
            db,
            row.id,
            EnrollmentCancelRequest(operator_name="测试", source="测试", note="家长暂缓"),
        )
        db.refresh(row)

        assert result["status"] == "cancelled"
        assert row.status == "cancelled"
        assert row.note == "家长暂缓"

        listed = list_enrollments(status="cancelled", page=1, page_size=20, db=db)
        assert listed.total == 1
        assert listed.data[0]["id"] == row.id
    finally:
        db.close()


def test_enrollment_stats_subject_split_and_mode_buckets():
    db = _make_session()
    try:
        _seed_enrollments(db)

        extra_student = Student(name="赵六", phone="13800000004")
        db.add(extra_student)
        db.flush()

        rows = [
            Enrollment(
                student_id=extra_student.id,
                grade="新高二暑",
                class_subjects=["英才物理", "英才化学"],
                class_mode="线上",
                mode_details=None,
                base_price=2000,
                discount_total=0,
                final_price=2000,
                discount_info={},
                non_price_benefits={"notes": []},
                pricing_formula="base",
                pricing_snapshot={"version": 1},
                quote_valid_until=_utcnow_naive(),
                quote_fingerprint="fp-4",
                status="increased",
                valid=True,
                operator_name="测试",
                source="测试",
                chain_root_enrollment_id=None,
                previous_enrollment_id=None,
            ),
            Enrollment(
                student_id=extra_student.id,
                grade="新高三暑",
                class_subjects=["英才化学"],
                class_mode="混合",
                mode_details={"offline_subjects": [], "online_subjects": ["英才化学"]},
                base_price=1500,
                discount_total=0,
                final_price=1500,
                discount_info={},
                non_price_benefits={"notes": []},
                pricing_formula="base",
                pricing_snapshot={"version": 1},
                quote_valid_until=_utcnow_naive(),
                quote_fingerprint="fp-5",
                status="partial_refunded",
                valid=True,
                operator_name="测试",
                source="测试",
                chain_root_enrollment_id=None,
                previous_enrollment_id=None,
            ),
            Enrollment(
                student_id=extra_student.id,
                grade="新高二暑",
                class_subjects=["英才数学"],
                class_mode="线下",
                mode_details=None,
                base_price=1000,
                discount_total=0,
                final_price=1000,
                discount_info={},
                non_price_benefits={"notes": []},
                pricing_formula="base",
                pricing_snapshot={"version": 1},
                quote_valid_until=_utcnow_naive(),
                quote_fingerprint="fp-6",
                status="refunded",
                valid=True,
                operator_name="测试",
                source="测试",
                chain_root_enrollment_id=None,
                previous_enrollment_id=None,
            ),
        ]
        db.add_all(rows)
        db.flush()
        for row in rows:
            row.chain_root_enrollment_id = row.id
        db.commit()

        stats = get_enrollment_stats(db)
        summary = stats["summary"]

        assert summary["total_rows"] == 3
        assert summary["total_enrollment_subject_units"] == 4
        assert summary["total_offline"] == 1
        assert summary["total_online"] == 3

        by_key = {(item["grade"], item["subject"]): item for item in stats["rows"]}

        physics = by_key[("新高二暑", "英才物理")]
        assert physics["offline_count"] == 1
        assert physics["online_count"] == 1
        assert physics["total_count"] == 2

        chemistry_g2 = by_key[("新高二暑", "英才化学")]
        assert chemistry_g2["offline_count"] == 0
        assert chemistry_g2["online_count"] == 1
        assert chemistry_g2["total_count"] == 1

        chemistry_g3 = by_key[("新高三暑", "英才化学")]
        assert chemistry_g3["offline_count"] == 0
        assert chemistry_g3["online_count"] == 1
        assert chemistry_g3["total_count"] == 1

        assert ("新高二暑", "英才数学") not in by_key
    finally:
        db.close()
