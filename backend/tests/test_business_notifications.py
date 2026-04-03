from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Enrollment, Student
from app.schemas import (
    BatchPayRequest,
    DiscountItem,
    PayRequest,
    QuoteCalculateRequest,
    RefundCreateRequest,
    StudentInfoInput,
)
from app.services import enrollment_service, refund_service


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def _seed_student(db, name: str = "李四", phone: str = "13800000002") -> Student:
    student = Student(name=name, phone=phone)
    db.add(student)
    db.flush()
    return student


def _seed_enrollment(db, student_id: int, status: str, final_price: float) -> Enrollment:
    enrollment = Enrollment(
        student_id=student_id,
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
        quote_fingerprint=f"fp-{status}-{final_price}",
        status=status,
        valid=True,
        operator_name="测试",
        source="测试",
    )
    db.add(enrollment)
    db.flush()
    return enrollment


def _build_adjust_payload(source: str = "测试") -> QuoteCalculateRequest:
    return QuoteCalculateRequest(
        operator_name="测试",
        source=source,
        student_info=StudentInfoInput(name="李四", phone="13800000002"),
        grade="新高二暑",
        class_subjects=["英才数学"],
        class_mode="线下",
        mode_details=None,
        discounts=[DiscountItem(name="现金优惠", amount=100)],
        note=None,
    )


def test_pay_enrollment_enqueues_payment_notice(monkeypatch):
    db = _make_session()
    try:
        student = _seed_student(db)
        enrollment = _seed_enrollment(db, student.id, status="quoted", final_price=980)
        db.commit()

        calls: list[tuple[str, str]] = []

        def _fake_enqueue_typed_text(db, message_type: str, text: str):
            calls.append((message_type, text))

        monkeypatch.setattr(enrollment_service.notification_service, "enqueue_typed_text", _fake_enqueue_typed_text)

        result = enrollment_service.pay_enrollment(
            db,
            enrollment.id,
            PayRequest(operator_name="财务", source="前台", note="现场已收款"),
        )

        assert result["status"] == "paid"
        assert calls
        assert calls[0][0] == "payment"
        assert "报名交费通知" in calls[0][1]
    finally:
        db.close()


def test_pay_batch_enqueues_payment_notice_for_each_success(monkeypatch):
    db = _make_session()
    try:
        student = _seed_student(db)
        e1 = _seed_enrollment(db, student.id, status="quoted", final_price=900)
        e2 = _seed_enrollment(db, student.id, status="quoted", final_price=1100)
        db.commit()

        sent_types: list[str] = []

        def _fake_enqueue_typed_text(db, message_type: str, text: str):
            sent_types.append(message_type)

        monkeypatch.setattr(enrollment_service.notification_service, "enqueue_typed_text", _fake_enqueue_typed_text)

        result = enrollment_service.pay_batch(
            db,
            BatchPayRequest(operator_name="财务", source="前台", enrollment_ids=[e1.id, e2.id]),
        )

        assert all(item["ok"] for item in result)
        assert sent_types == ["payment", "payment"]
    finally:
        db.close()


def test_adjustment_decrease_enqueues_adjustment_and_refund_notice(monkeypatch):
    db = _make_session()
    try:
        student = _seed_student(db)
        old = _seed_enrollment(db, student.id, status="paid", final_price=12000)
        db.commit()

        sent_types: list[str] = []

        def _fake_enqueue_typed_text(db, message_type: str, text: str):
            sent_types.append(message_type)

        monkeypatch.setattr(refund_service.notification_service, "enqueue_typed_text", _fake_enqueue_typed_text)

        payload = RefundCreateRequest(
            operator_name="教务",
            source="前台",
            original_enrollment_id=old.id,
            new_enrollment_payload=_build_adjust_payload(source="前台"),
            review_note="调整后应退",
        )
        result = refund_service.create_refund(db, payload)

        assert result["branch_type"] == "decrease"
        assert sent_types == ["adjustment", "refund"]
    finally:
        db.close()