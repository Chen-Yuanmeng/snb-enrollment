from datetime import UTC, datetime

from app.main import list_enrollments
from app.models import Enrollment, Student
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
            status="quoted",
            valid=True,
            operator_name="测试",
            source="测试",
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
            status="paid",
            valid=True,
            operator_name="测试",
            source="测试",
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
            status="quoted",
            valid=True,
            operator_name="测试",
            source="测试",
        ),
    ]
    db.add_all(enrollments)
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
        result = list_enrollments(status="quoted", page=1, page_size=20, db=db)
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
