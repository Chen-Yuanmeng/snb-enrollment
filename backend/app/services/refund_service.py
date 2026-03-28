from typing import Any, cast

from sqlalchemy.orm import Session

from app.constants import STATUS_PAID, STATUS_REFUNDED, STATUS_REFUND_REQUESTED
from app.errors import raise_biz_error
from app.models import Enrollment, Refund
from app.pricing_engine import build_quote
from app.schemas import QuoteCalculateRequest, RefundCreateRequest, RefundPreviewRequest
from app.services.shared_service import inject_auto_discounts, log_operation


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
    refund_amount = round(old_price - new_price, 2)

    auto_rejected = refund_amount <= 0
    reject_reason = "差额小于等于0，需人工先全退原报名再新建" if auto_rejected else None

    return {
        "old_price": old_price,
        "new_price": new_price,
        "refund_amount": refund_amount,
        "auto_rejected": auto_rejected,
        "reject_reason": reject_reason,
    }


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
    refund_amount = round(old_price - new_price, 2)

    old.status = STATUS_REFUND_REQUESTED

    auto_rejected = refund_amount <= 0
    reject_reason = None

    if auto_rejected:
        reject_reason = "差额小于等于0，需人工先全退原报名再新建"
    else:
        old.status = STATUS_REFUNDED

    refund = Refund(
        original_enrollment_id=old.id,
        recalculated_enrollment_id=None,
        refund_class_subjects=effective_payload.class_subjects,
        old_price=old_price,
        new_price=new_price,
        refund_amount=refund_amount,
        auto_rejected=auto_rejected,
        reject_reason=reject_reason,
        review_required=True,
        review_operator_name=payload.operator_name,
        review_note=payload.review_note,
        operator_name=payload.operator_name,
        source=payload.source,
    )
    db.add(refund)
    db.flush()

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_refund",
        target_type="refund",
        target_id=refund.id,
        result_status="auto_rejected" if auto_rejected else "success",
        message=reject_reason,
    )
    db.commit()

    if auto_rejected:
        raise_biz_error(40006, reject_reason or "退费金额小于等于0（自动拒绝）")

    return {"refund_id": refund.id, "refund_amount": refund_amount}
