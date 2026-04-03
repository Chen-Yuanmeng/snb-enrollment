from typing import Any, cast

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.constants import (
    ADJUSTMENT_STATUS_ADJUSTED,
    ADJUSTMENT_STATUS_PENDING,
    ADJUSTMENT_TYPE_DECREASE,
    ADJUSTMENT_TYPE_EQUAL,
    ADJUSTMENT_TYPE_INCREASE,
    STATUS_ADJUSTED,
    STATUS_CONFIRMED,
    STATUS_INCREASED,
    STATUS_PENDING_ADJUSTMENT,
    STATUS_PARTIAL_REFUNDED,
    STATUS_REFUNDED,
    STATUS_UNCONFIRMED,
)
from app.core.datetime_utils import utcnow_naive
from app.errors import raise_biz_error
from app.models import Enrollment, Refund, Student
from app.pricing_engine import build_fingerprint, build_quote
from app.schemas import (
    AdjustmentConfirmPaymentRequest,
    QuoteCalculateRequest,
    RefundConfirmRequest,
    RefundCreateRequest,
    RefundPreviewRequest,
)
from app.services import notification_service
from app.services.shared_service import get_or_create_student, inject_auto_discounts, log_operation


def _build_notice_text(
    branch_type: str,
    original_enrollment_id: int,
    old_price: float,
    new_price: float,
    delta_amount: float,
    recalculated_enrollment_id: int | None = None,
    refund_id: int | None = None,
) -> str:
    if branch_type == "increase":
        return (
            "【报名调整通知】\n"
            f"原报名ID：{original_enrollment_id}\n"
            f"原金额：{old_price:.2f}\n"
            f"调整后金额：{new_price:.2f}\n"
            f"需补交：{delta_amount:.2f}\n"
            f"新报名ID：{recalculated_enrollment_id or '-'}\n"
            "状态：待确认缴费"
        )
    if branch_type == "decrease":
        return (
            "【报名调整通知】\n"
            f"原报名ID：{original_enrollment_id}\n"
            f"原金额：{old_price:.2f}\n"
            f"调整后金额：{new_price:.2f}\n"
            f"应退金额：{delta_amount:.2f}\n"
            f"退费单ID：{refund_id or '-'}\n"
            "状态：退费处理中"
        )
    return (
        "【报名调整通知】\n"
        f"原报名ID：{original_enrollment_id}\n"
        f"原金额：{old_price:.2f}\n"
        f"调整后金额：{new_price:.2f}\n"
        "差额：0.00\n"
        "状态：无需补交或退费"
    )


def _build_refund_notice_text(
    original_enrollment_id: int,
    old_price: float,
    new_price: float,
    refund_amount: float,
    refund_id: int,
) -> str:
    return (
        "【退费通知】\n"
        f"原报名ID：{original_enrollment_id}\n"
        f"原金额：{old_price:.2f}\n"
        f"调整后金额：{new_price:.2f}\n"
        f"应退金额：{refund_amount:.2f}\n"
        f"退费单ID：{refund_id}\n"
        "状态：待审核"
    )


def _safe_enqueue_notice(db: Session, message_type: str, text: str) -> None:
    try:
        notification_service.enqueue_typed_text(db=db, message_type=message_type, text=text)
    except Exception:
        # 通知链路异常不影响报名调整/退费主流程。
        pass


def _build_adjustment_preview(old_price: float, new_price: float, original_enrollment_id: int) -> dict[str, Any]:
    delta_amount = round(abs(new_price - old_price), 2)
    if new_price > old_price:
        branch_type = ADJUSTMENT_TYPE_INCREASE
        payable_amount = delta_amount
        refundable_amount = 0.0
        hint = "将新增一条未确认的调整后报名记录"
    elif new_price < old_price:
        branch_type = ADJUSTMENT_TYPE_DECREASE
        payable_amount = 0.0
        refundable_amount = delta_amount
        hint = "将新增一条未确认报名并生成退费任务"
    else:
        branch_type = ADJUSTMENT_TYPE_EQUAL
        payable_amount = 0.0
        refundable_amount = 0.0
        hint = "金额无变化，也会生成待确认调整记录"

    return {
        "branch_type": branch_type,
        "old_price": old_price,
        "new_price": new_price,
        "delta_amount": delta_amount,
        "payable_amount": payable_amount,
        "refundable_amount": refundable_amount,
        "related_ids": {
            "original_enrollment_id": original_enrollment_id,
            "recalculated_enrollment_id": None,
            "refund_id": None,
        },
        "notice_text": _build_notice_text(
            branch_type=branch_type,
            original_enrollment_id=original_enrollment_id,
            old_price=old_price,
            new_price=new_price,
            delta_amount=delta_amount,
        ),
        "hint": hint,
    }


def preview_refund(db: Session, payload: RefundPreviewRequest) -> dict[str, Any]:
    if payload.new_enrollment_payload.source != payload.source:
        raise_biz_error(40001, "退费请求中的source不一致")
    old = db.get(Enrollment, payload.original_enrollment_id)
    if old is None:
        raise_biz_error(40401, "原报名记录不存在", status_code=404)
    old = cast(Enrollment, old)

    try:
        effective_payload = cast(QuoteCalculateRequest, inject_auto_discounts(db, payload.new_enrollment_payload))
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))

    old_price = float(old.final_price)
    new_price = quote.final_price
    return _build_adjustment_preview(
        old_price=old_price,
        new_price=new_price,
        original_enrollment_id=old.id,
    )


def create_refund(db: Session, payload: RefundCreateRequest) -> dict[str, Any]:
    if payload.new_enrollment_payload.source != payload.source:
        raise_biz_error(40001, "退费请求中的source不一致")
    old = db.get(Enrollment, payload.original_enrollment_id)
    if old is None:
        raise_biz_error(40401, "原报名记录不存在", status_code=404)
    old = cast(Enrollment, old)
    if old.status not in {STATUS_CONFIRMED, STATUS_INCREASED, STATUS_PARTIAL_REFUNDED, "paid"}:
        raise_biz_error(40005, "仅已确认状态可发起调整")

    try:
        effective_payload = cast(QuoteCalculateRequest, inject_auto_discounts(db, payload.new_enrollment_payload))
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))

    old_price = float(old.final_price)
    new_price = quote.final_price
    delta_amount = round(abs(new_price - old_price), 2)

    student = get_or_create_student(db, effective_payload)
    fingerprint = build_fingerprint(student.id, effective_payload, quote.final_price)

    if new_price > old_price:
        branch_type = ADJUSTMENT_TYPE_INCREASE
    elif new_price < old_price:
        branch_type = ADJUSTMENT_TYPE_DECREASE
    else:
        branch_type = ADJUSTMENT_TYPE_EQUAL

    old.status = STATUS_PENDING_ADJUSTMENT
    old.updated_at = utcnow_naive()

    recalculated = Enrollment(
        student_id=student.id,
        grade=effective_payload.grade,
        class_subjects=effective_payload.class_subjects,
        class_mode=effective_payload.class_mode,
        mode_details=effective_payload.mode_details,
        base_price=quote.base_price,
        discount_total=quote.discount_total,
        final_price=quote.final_price,
        discount_info=quote.discount_info,
        non_price_benefits={"notes": quote.non_price_benefits},
        pricing_formula=quote.pricing_formula,
        pricing_snapshot=quote.pricing_snapshot,
        quote_valid_until=quote.quote_valid_until,
        quote_fingerprint=fingerprint,
        status=STATUS_UNCONFIRMED,
        valid=True,
        operator_name=effective_payload.operator_name,
        source=effective_payload.source,
        chain_root_enrollment_id=old.chain_root_enrollment_id or old.id,
        previous_enrollment_id=old.id,
        note=f"报名调整生成，原报名ID={old.id}，类型={branch_type}",
    )
    db.add(recalculated)
    db.flush()

    payable_amount = delta_amount if branch_type == ADJUSTMENT_TYPE_INCREASE else 0.0
    refundable_amount = delta_amount if branch_type == ADJUSTMENT_TYPE_DECREASE else 0.0

    refund = Refund(
        original_enrollment_id=old.id,
        recalculated_enrollment_id=recalculated.id,
        refund_class_subjects=effective_payload.class_subjects,
        old_price=old_price,
        new_price=new_price,
        refund_amount=refundable_amount,
        auto_rejected=False,
        reject_reason=None,
        review_required=True,
        review_operator_name=payload.operator_name,
        review_note=payload.review_note,
        operator_name=payload.operator_name,
        source=payload.source,
        task_type=branch_type,
        status=ADJUSTMENT_STATUS_PENDING,
        note="报名调整任务",
    )
    db.add(refund)
    db.flush()

    notice_text = _build_notice_text(
        branch_type=branch_type,
        original_enrollment_id=old.id,
        old_price=old_price,
        new_price=new_price,
        delta_amount=delta_amount,
        recalculated_enrollment_id=recalculated.id,
        refund_id=refund.id,
    )
    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_adjustment",
        target_type="refund",
        target_id=refund.id,
        result_status="success",
        message=f"原报名ID={old.id}，类型={branch_type}，差额={delta_amount:.2f}",
    )
    db.commit()
    _safe_enqueue_notice(db, "adjustment", notice_text)
    if branch_type == ADJUSTMENT_TYPE_DECREASE:
        _safe_enqueue_notice(
            db,
            "refund",
            _build_refund_notice_text(
                original_enrollment_id=old.id,
                old_price=old_price,
                new_price=new_price,
                refund_amount=delta_amount,
                refund_id=refund.id,
            ),
        )

    return {
        "branch_type": branch_type,
        "old_price": old_price,
        "new_price": new_price,
        "delta_amount": delta_amount,
        "payable_amount": payable_amount,
        "refundable_amount": refundable_amount,
        "related_ids": {
            "original_enrollment_id": old.id,
            "recalculated_enrollment_id": recalculated.id,
            "refund_id": refund.id,
        },
        "notice_text": notice_text,
    }


def list_pending_adjustments(db: Session, keyword: str | None = None) -> dict[str, Any]:
    stmt = (
        select(
            Refund,
            Enrollment,
            Student.name.label("student_name"),
            Student.phone.label("student_phone"),
        )
        .join(Enrollment, Refund.original_enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
    )
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            if trimmed.isdigit():
                value = int(trimmed)
                stmt = stmt.where(
                    or_(
                        Student.name.ilike(f"%{trimmed}%"),
                        Refund.id == value,
                        Refund.original_enrollment_id == value,
                        Refund.recalculated_enrollment_id == value,
                    )
                )
            else:
                stmt = stmt.where(Student.name.ilike(f"%{trimmed}%"))

    rows = db.execute(stmt.order_by(desc(Refund.id))).all()
    items: list[dict[str, Any]] = []
    for task, original_enrollment, student_name, _student_phone in rows:
        payable_amount = max(0.0, float(task.new_price) - float(task.old_price))
        refundable_amount = float(task.refund_amount or 0)
        if task.task_type == ADJUSTMENT_TYPE_DECREASE and refundable_amount <= 0:
            refundable_amount = round(max(0.0, float(task.old_price) - float(task.new_price)), 2)
        items.append(
            {
                "task_type": task.task_type,
                "status": task.status,
                "enrollment_id": task.recalculated_enrollment_id,
                "refund_id": task.id,
                "original_enrollment_id": task.original_enrollment_id,
                "student_name": student_name,
                "grade": original_enrollment.grade,
                "class_subjects": task.refund_class_subjects,
                "payable_amount": round(payable_amount, 2),
                "refundable_amount": round(refundable_amount, 2),
                "created_at": task.created_at,
            }
        )
    return {"items": items, "total": len(items)}


def confirm_adjustment_payment(
    db: Session,
    enrollment_id: int,
    payload: AdjustmentConfirmPaymentRequest,
) -> dict[str, Any]:
    task_stmt = (
        select(Refund)
        .where(Refund.recalculated_enrollment_id == enrollment_id)
        .order_by(desc(Refund.id))
    )
    task = db.scalar(task_stmt)
    if task is None:
        raise_biz_error(40401, "调整记录不存在", status_code=404)
    task = cast(Refund, task)
    if task.task_type == ADJUSTMENT_TYPE_DECREASE:
        raise_biz_error(40005, "退费记录请走退费确认接口")
    if task.status == ADJUSTMENT_STATUS_ADJUSTED:
        return {
            "refund_id": task.id,
            "enrollment_id": enrollment_id,
            "status": task.status,
        }

    original = db.get(Enrollment, task.original_enrollment_id)
    recalculated = db.get(Enrollment, enrollment_id)
    if original is None or recalculated is None:
        raise_biz_error(40401, "报名记录不存在", status_code=404)
    original = cast(Enrollment, original)
    recalculated = cast(Enrollment, recalculated)

    if recalculated.status != STATUS_UNCONFIRMED:
        raise_biz_error(40005, "调整后报名状态非法")

    recalculated.status = STATUS_INCREASED if task.task_type == ADJUSTMENT_TYPE_INCREASE else STATUS_CONFIRMED
    recalculated.updated_at = utcnow_naive()
    original.status = STATUS_ADJUSTED
    original.updated_at = utcnow_naive()

    task.status = ADJUSTMENT_STATUS_ADJUSTED
    task.confirmed_at = utcnow_naive()
    if payload.note:
        task.review_note = payload.note

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="confirm_adjustment",
        target_type="refund",
        target_id=task.id,
        result_status="success",
        message=f"调整确认，原报名ID={original.id}，新报名ID={recalculated.id}",
    )
    db.commit()
    return {
        "refund_id": task.id,
        "enrollment_id": recalculated.id,
        "status": task.status,
        "original_status": original.status,
        "new_status": recalculated.status,
    }


def confirm_refund(db: Session, refund_id: int, payload: RefundConfirmRequest) -> dict[str, Any]:
    task = db.get(Refund, refund_id)
    if task is None:
        raise_biz_error(40401, "退费记录不存在", status_code=404)
    task = cast(Refund, task)
    if task.task_type != ADJUSTMENT_TYPE_DECREASE:
        raise_biz_error(40005, "仅退费类型可走此确认接口")
    if task.status == ADJUSTMENT_STATUS_ADJUSTED:
        return {
            "refund_id": task.id,
            "status": task.status,
        }

    original = db.get(Enrollment, task.original_enrollment_id)
    recalculated = db.get(Enrollment, task.recalculated_enrollment_id) if task.recalculated_enrollment_id else None
    if original is None or recalculated is None:
        raise_biz_error(40401, "报名记录不存在", status_code=404)
    original = cast(Enrollment, original)
    recalculated = cast(Enrollment, recalculated)

    is_partial_refund = float(task.new_price) > 0
    original.status = STATUS_ADJUSTED if is_partial_refund else STATUS_REFUNDED
    original.updated_at = utcnow_naive()
    recalculated.status = STATUS_PARTIAL_REFUNDED if is_partial_refund else STATUS_REFUNDED
    recalculated.updated_at = utcnow_naive()

    task.status = ADJUSTMENT_STATUS_ADJUSTED
    task.confirmed_at = utcnow_naive()
    if payload.note:
        task.review_note = payload.note

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="confirm_refund",
        target_type="refund",
        target_id=task.id,
        result_status="success",
        message=f"退费确认，原报名ID={original.id}，新报名ID={recalculated.id}",
    )
    db.commit()
    return {
        "refund_id": task.id,
        "status": task.status,
        "original_status": original.status,
        "new_status": recalculated.status,
    }
