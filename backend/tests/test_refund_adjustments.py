from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Enrollment, Refund, Student
from app.pricing_engine import build_quote
from app.schemas import (
    DiscountItem,
    QuoteCalculateRequest,
    RefundCreateRequest,
    StudentInfoInput,
)
from app.services import refund_service


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def _build_new_payload() -> QuoteCalculateRequest:
    return QuoteCalculateRequest(
        operator_name="测试",
        source="测试",
        student_info=StudentInfoInput(name="李四", phone="13800000002"),
        grade="新高二暑",
        class_subjects=["英才数学"],
        class_mode="线下",
        mode_details=None,
        discounts=[DiscountItem(name="现金优惠", amount=100)],
        note=None,
    )


def _seed_paid_enrollment(db, final_price: float) -> Enrollment:
    student = Student(name="李四", phone="13800000002")
    db.add(student)
    db.flush()

    enrollment = Enrollment(
        student_id=student.id,
        grade="新高二暑",
        class_subjects=["英才数学", "英才物理"],
        class_mode="线下",
        mode_details=None,
        base_price=1000,
        discount_total=0,
        final_price=final_price,
        discount_info={},
        non_price_benefits={"notes": []},
        pricing_formula="test",
        pricing_snapshot={"version": 1},
        quote_valid_until=_utcnow_naive(),
        quote_fingerprint="fp-old",
        status="paid",
        valid=True,
        operator_name="测试",
        source="测试",
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def _build_request(original_enrollment_id: int) -> RefundCreateRequest:
    new_payload = _build_new_payload()
    return RefundCreateRequest(
        operator_name="测试",
        source="测试",
        original_enrollment_id=original_enrollment_id,
        new_enrollment_payload=new_payload,
        review_note="调整备注",
    )


def test_adjustment_increase_creates_new_enrollment():
    db = _make_session()
    try:
        old = _seed_paid_enrollment(db, final_price=1000)
        result = refund_service.create_refund(db, _build_request(old.id))

        assert result["branch_type"] == "increase"
        assert result["payable_amount"] > 0
        assert result["related_ids"]["recalculated_enrollment_id"] is not None
        assert result["related_ids"]["refund_id"] is None

        new_enrollment = db.get(Enrollment, result["related_ids"]["recalculated_enrollment_id"])
        assert new_enrollment is not None
        assert new_enrollment.status == "quoted"

        refund_count = db.query(Refund).count()
        assert refund_count == 0
    finally:
        db.close()


def test_adjustment_decrease_creates_refund_record():
    db = _make_session()
    try:
        old = _seed_paid_enrollment(db, final_price=12000)
        result = refund_service.create_refund(db, _build_request(old.id))

        assert result["branch_type"] == "decrease"
        assert result["refundable_amount"] > 0
        assert result["related_ids"]["refund_id"] is not None

        refreshed_old = db.get(Enrollment, old.id)
        assert refreshed_old is not None
        assert refreshed_old.status == "refund_requested"

        refund = db.get(Refund, result["related_ids"]["refund_id"])
        assert refund is not None
        assert float(refund.refund_amount) == result["refundable_amount"]
    finally:
        db.close()


def test_adjustment_equal_generates_notice_only():
    db = _make_session()
    try:
        new_payload = _build_new_payload()
        quote = build_quote(new_payload)
        old = _seed_paid_enrollment(db, final_price=quote.final_price)

        result = refund_service.create_refund(db, _build_request(old.id))

        assert result["branch_type"] == "equal"
        assert result["delta_amount"] == 0
        assert result["payable_amount"] == 0
        assert result["refundable_amount"] == 0
        assert result["related_ids"]["recalculated_enrollment_id"] is None
        assert result["related_ids"]["refund_id"] is None
        assert "无需补交或退费" in result["notice_text"]
    finally:
        db.close()
