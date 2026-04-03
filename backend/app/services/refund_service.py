from typing import Any, cast

from sqlalchemy.orm import Session

from app.constants import STATUS_PAID, STATUS_QUOTED, STATUS_REFUND_REQUESTED
from app.core.datetime_utils import utcnow_naive
from app.errors import raise_biz_error
from app.models import Enrollment, Refund
from app.pricing_engine import build_fingerprint, build_quote
from app.schemas import QuoteCalculateRequest, RefundCreateRequest, RefundPreviewRequest
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
        branch_type = "increase"
        payable_amount = delta_amount
        refundable_amount = 0.0
        hint = "将新增一条待确认缴费的报名记录"
    elif new_price < old_price:
        branch_type = "decrease"
        payable_amount = 0.0
        refundable_amount = delta_amount
        hint = "将生成退费记录并提示应退金额"
    else:
        branch_type = "equal"
        payable_amount = 0.0
        refundable_amount = 0.0
        hint = "金额无变化，仅生成调整提示"

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
    if old.status != STATUS_PAID:
        raise_biz_error(40005, "仅已缴费状态可申请退费")

    try:
        effective_payload = cast(QuoteCalculateRequest, inject_auto_discounts(db, payload.new_enrollment_payload))
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))

    old_price = float(old.final_price)
    new_price = quote.final_price
    delta_amount = round(abs(new_price - old_price), 2)

    if new_price > old_price:
        student = get_or_create_student(db, effective_payload)
        fingerprint = build_fingerprint(student.id, effective_payload, quote.final_price)
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
            status=STATUS_QUOTED,
            valid=True,
            operator_name=effective_payload.operator_name,
            source=effective_payload.source,
            note=f"报名调整补交，原报名ID={old.id}",
        )
        db.add(recalculated)
        db.flush()

        notice_text = _build_notice_text(
            branch_type="increase",
            original_enrollment_id=old.id,
            old_price=old_price,
            new_price=new_price,
            delta_amount=delta_amount,
            recalculated_enrollment_id=recalculated.id,
        )
        log_operation(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="create_adjustment_enrollment",
            target_type="enrollment",
            target_id=recalculated.id,
            result_status="success",
            message=f"原报名ID={old.id}，需补交={delta_amount:.2f}",
        )
        db.commit()
        _safe_enqueue_notice(db, "adjustment", notice_text)
        return {
            "branch_type": "increase",
            "old_price": old_price,
            "new_price": new_price,
            "delta_amount": delta_amount,
            "payable_amount": delta_amount,
            "refundable_amount": 0.0,
            "related_ids": {
                "original_enrollment_id": old.id,
                "recalculated_enrollment_id": recalculated.id,
                "refund_id": None,
            },
            "notice_text": notice_text,
        }

    if new_price < old_price:
        old.status = STATUS_REFUND_REQUESTED
        old.updated_at = utcnow_naive()

        refund = Refund(
            original_enrollment_id=old.id,
            recalculated_enrollment_id=None,
            refund_class_subjects=effective_payload.class_subjects,
            old_price=old_price,
            new_price=new_price,
            refund_amount=delta_amount,
            auto_rejected=False,
            reject_reason=None,
            review_required=True,
            review_operator_name=payload.operator_name,
            review_note=payload.review_note,
            operator_name=payload.operator_name,
            source=payload.source,
            note="报名调整退费",
        )
        db.add(refund)
        db.flush()

        notice_text = _build_notice_text(
            branch_type="decrease",
            original_enrollment_id=old.id,
            old_price=old_price,
            new_price=new_price,
            delta_amount=delta_amount,
            refund_id=refund.id,
        )
        log_operation(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="create_refund",
            target_type="refund",
            target_id=refund.id,
            result_status="success",
            message=f"原报名ID={old.id}，应退={delta_amount:.2f}",
        )
        db.commit()
        _safe_enqueue_notice(db, "adjustment", notice_text)
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
            "branch_type": "decrease",
            "old_price": old_price,
            "new_price": new_price,
            "delta_amount": delta_amount,
            "payable_amount": 0.0,
            "refundable_amount": delta_amount,
            "related_ids": {
                "original_enrollment_id": old.id,
                "recalculated_enrollment_id": None,
                "refund_id": refund.id,
            },
            "notice_text": notice_text,
        }

    notice_text = _build_notice_text(
        branch_type="equal",
        original_enrollment_id=old.id,
        old_price=old_price,
        new_price=new_price,
        delta_amount=0.0,
    )
    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_adjustment_notice",
        target_type="enrollment",
        target_id=old.id,
        result_status="success",
        message="金额无变化",
    )
    db.commit()
    _safe_enqueue_notice(db, "adjustment", notice_text)
    return {
        "branch_type": "equal",
        "old_price": old_price,
        "new_price": new_price,
        "delta_amount": 0.0,
        "payable_amount": 0.0,
        "refundable_amount": 0.0,
        "related_ids": {
            "original_enrollment_id": old.id,
            "recalculated_enrollment_id": None,
            "refund_id": None,
        },
        "notice_text": notice_text,
    }
