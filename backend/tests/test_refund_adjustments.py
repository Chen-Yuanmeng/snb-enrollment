from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Enrollment, Refund, Student
from app.pricing_engine import build_quote
from app.schemas import (
    AdjustmentConfirmPaymentRequest,
    DiscountItem,
    QuoteCalculateRequest,
    RefundConfirmRequest,
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
        status="confirmed",
        valid=True,
        operator_name="测试",
        source="测试",
        chain_root_enrollment_id=None,
        previous_enrollment_id=None,
    )
    db.add(enrollment)
    db.flush()
    enrollment.chain_root_enrollment_id = enrollment.id
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
        assert result["related_ids"]["refund_id"] is not None

        refreshed_old = db.get(Enrollment, old.id)
        assert refreshed_old is not None
        assert refreshed_old.status == "pending_adjustment"

        new_enrollment = db.get(Enrollment, result["related_ids"]["recalculated_enrollment_id"])
        assert new_enrollment is not None
        assert new_enrollment.status == "unconfirmed"
        assert new_enrollment.previous_enrollment_id == old.id

        refund_task = db.get(Refund, result["related_ids"]["refund_id"])
        assert refund_task is not None
        assert refund_task.task_type == "increase"
        assert refund_task.status == "pending"
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
        assert result["related_ids"]["recalculated_enrollment_id"] is not None

        refreshed_old = db.get(Enrollment, old.id)
        assert refreshed_old is not None
        assert refreshed_old.status == "pending_adjustment"

        recalculated = db.get(Enrollment, result["related_ids"]["recalculated_enrollment_id"])
        assert recalculated is not None
        assert recalculated.status == "unconfirmed"

        refund = db.get(Refund, result["related_ids"]["refund_id"])
        assert refund is not None
        assert float(refund.refund_amount) == result["refundable_amount"]
        assert refund.task_type == "decrease"
        assert refund.status == "pending"
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
        assert result["related_ids"]["recalculated_enrollment_id"] is not None
        assert result["related_ids"]["refund_id"] is not None
        task = db.get(Refund, result["related_ids"]["refund_id"])
        assert task is not None
        assert task.task_type == "equal"
        assert task.status == "pending"
        assert "无需补交或退费" in result["notice_text"]
    finally:
        db.close()


def test_confirm_adjustment_payment_updates_chain_statuses():
    db = _make_session()
    try:
        old = _seed_paid_enrollment(db, final_price=1000)
        result = refund_service.create_refund(db, _build_request(old.id))
        assert result["branch_type"] == "increase"

        confirm = refund_service.confirm_adjustment_payment(
            db,
            enrollment_id=result["related_ids"]["recalculated_enrollment_id"],
            payload=AdjustmentConfirmPaymentRequest(operator_name="测试", source="测试", note="确认调整"),
        )
        assert confirm["status"] == "adjusted"
        assert confirm["new_status"] == "increased"
        assert confirm["original_status"] == "adjusted"
    finally:
        db.close()


def test_confirm_refund_updates_chain_statuses():
    db = _make_session()
    try:
        old = _seed_paid_enrollment(db, final_price=12000)
        result = refund_service.create_refund(db, _build_request(old.id))
        assert result["branch_type"] == "decrease"

        confirm = refund_service.confirm_refund(
            db,
            refund_id=result["related_ids"]["refund_id"],
            payload=RefundConfirmRequest(operator_name="测试", source="测试", note="确认退费"),
        )
        assert confirm["status"] == "adjusted"
        assert confirm["new_status"] == "partial_refunded"
        assert confirm["original_status"] == "adjusted"
    finally:
        db.close()
