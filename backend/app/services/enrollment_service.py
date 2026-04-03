from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.constants import STATUS_PAID, STATUS_QUOTED
from app.core.datetime_utils import utcnow_naive
from app.errors import raise_biz_error
from app.models import Enrollment, Student
from app.pricing_engine import build_fingerprint, build_quote
from app.schemas import BatchPayRequest, EnrollmentCreateRequest, EnrollmentOut, PayRequest
from app.services import notification_service
from app.services.shared_service import get_or_create_student, inject_auto_discounts, log_operation


def _render_payment_notice(enrollment: Enrollment, student: Student | None) -> str:
    return "\n".join(
        [
            "【报名交费通知】",
            f"报名ID: {enrollment.id}",
            f"学生: {student.name if student and student.name else '-'}",
            f"手机号: {student.phone if student and student.phone else '-'}",
            f"年级: {enrollment.grade}",
            f"科目: {'、'.join(enrollment.class_subjects or []) or '-'}",
            f"实收金额: ¥{float(enrollment.final_price):.2f}",
            f"算式: {enrollment.pricing_formula}",
            f"来源: {enrollment.source or '-'}",
            "状态: 已交费",
        ]
    )


def create_enrollment(db: Session, payload: EnrollmentCreateRequest) -> dict[str, Any]:
    try:
        effective_payload = cast(EnrollmentCreateRequest, inject_auto_discounts(db, payload))
        quote = build_quote(effective_payload)
        student = get_or_create_student(db, payload)
        fingerprint = build_fingerprint(student.id, effective_payload, quote.final_price)

        dup_stmt = select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.grade == payload.grade,
            Enrollment.quote_fingerprint == fingerprint,
            Enrollment.final_price == quote.final_price,
            Enrollment.valid.is_(True),
        )
        duplicate = db.scalar(dup_stmt)
        if duplicate:
            raise_biz_error(40003, "重复提交")

        row = Enrollment(
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
            note=effective_payload.note,
        )
        db.add(row)
        db.flush()

        log_operation(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="create_enrollment",
            target_type="enrollment",
            target_id=row.id,
            result_status="success",
            request_summary={
                "student_id": student.id,
                "grade": effective_payload.grade,
                "class_subjects": effective_payload.class_subjects,
                "source": payload.source,
            },
        )
        db.commit()
        return {"enrollment_id": row.id, "status": row.status}
    except ValueError as exc:
        db.rollback()
        raise_biz_error(40001, str(exc))
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise_biz_error(50000, str(exc), status_code=500)

    raise RuntimeError("unreachable")


def list_enrollments(
    db: Session,
    status: str | None = None,
    student_id: int | None = None,
    grade: str | None = None,
    valid: bool | None = None,
    source: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
) -> dict[str, Any]:
    normalized_page = page if isinstance(page, int) else 1
    normalized_page_size = page_size if isinstance(page_size, int) else 20
    normalized_limit = limit if isinstance(limit, int) else None

    effective_page_size = normalized_limit if normalized_limit is not None else normalized_page_size
    effective_page = 1 if normalized_limit is not None else normalized_page

    data_stmt = select(Enrollment, Student.name.label("student_name"), Student.phone.label("student_phone")).join(
        Student, Enrollment.student_id == Student.id
    )
    count_stmt = select(func.count()).select_from(Enrollment).join(Student, Enrollment.student_id == Student.id)

    filters = []
    if status:
        filters.append(Enrollment.status == status)
    if student_id:
        filters.append(Enrollment.student_id == student_id)
    if grade:
        filters.append(Enrollment.grade == grade)
    if valid is not None:
        filters.append(Enrollment.valid.is_(valid))
    if source:
        filters.append(Enrollment.source == source)
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            if trimmed.isdigit():
                filters.append(or_(Student.name.ilike(f"%{trimmed}%"), Enrollment.id == int(trimmed)))
            else:
                filters.append(Student.name.ilike(f"%{trimmed}%"))

    if filters:
        data_stmt = data_stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)

    rows = db.execute(
        data_stmt
        .order_by(desc(Enrollment.id))
        .offset((effective_page - 1) * effective_page_size)
        .limit(effective_page_size)
    ).all()
    data: list[dict[str, Any]] = []
    for enrollment, student_name, student_phone in rows:
        item = EnrollmentOut.model_validate(enrollment).model_dump()
        item["student_name"] = student_name or ""
        item["student_phone"] = student_phone or ""
        item["discount_info"] = enrollment.discount_info or {}
        item["pricing_snapshot"] = enrollment.pricing_snapshot or {}
        item["base_price"] = float(enrollment.base_price)
        item["discount_total"] = float(enrollment.discount_total)
        data.append(item)

    return {
        "data": data,
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
    }


def get_enrollment(db: Session, enrollment_id: int) -> dict[str, Any]:
    row = db.get(Enrollment, enrollment_id)
    if row is None:
        raise_biz_error(40401, "记录不存在", status_code=404)
    row = cast(Enrollment, row)
    return {
        "id": row.id,
        "student_id": row.student_id,
        "grade": row.grade,
        "class_subjects": row.class_subjects,
        "class_mode": row.class_mode,
        "base_price": float(row.base_price),
        "discount_total": float(row.discount_total),
        "final_price": float(row.final_price),
        "discount_info": row.discount_info,
        "non_price_benefits": row.non_price_benefits,
        "pricing_formula": row.pricing_formula,
        "pricing_snapshot": row.pricing_snapshot,
        "quote_valid_until": row.quote_valid_until,
        "status": row.status,
        "operator_name": row.operator_name,
        "source": row.source,
        "created_at": row.created_at,
    }


def pay_enrollment(db: Session, enrollment_id: int, payload: PayRequest) -> dict[str, Any]:
    row = db.get(Enrollment, enrollment_id)
    if row is None:
        raise_biz_error(40401, "记录不存在", status_code=404)
    row = cast(Enrollment, row)
    if row.status != STATUS_QUOTED:
        raise_biz_error(40005, "状态流转非法")

    row.status = STATUS_PAID
    row.updated_at = utcnow_naive()
    row.note = payload.note or row.note

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="pay_enrollment",
        target_type="enrollment",
        target_id=row.id,
        result_status="success",
    )
    db.commit()

    student = db.get(Student, row.student_id)
    try:
        notification_service.enqueue_typed_text(
            db=db,
            message_type="payment",
            text=_render_payment_notice(row, student),
        )
    except Exception:
        # 通知链路异常不影响交费主流程。
        pass

    return {"enrollment_id": row.id, "status": row.status}


def pay_batch(db: Session, payload: BatchPayRequest) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    paid_ids: list[int] = []

    for enrollment_id in payload.enrollment_ids:
        row = db.get(Enrollment, enrollment_id)
        if not row:
            results.append({"enrollment_id": enrollment_id, "ok": False, "reason": "not found"})
            continue
        if row.status != STATUS_QUOTED:
            results.append({"enrollment_id": enrollment_id, "ok": False, "reason": "invalid status"})
            continue
        row.status = STATUS_PAID
        row.updated_at = utcnow_naive()
        results.append({"enrollment_id": enrollment_id, "ok": True})
        paid_ids.append(row.id)

        log_operation(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="pay_enrollment_batch",
            target_type="enrollment",
            target_id=row.id,
            result_status="success",
        )

    db.commit()

    for enrollment_id in paid_ids:
        paid = db.get(Enrollment, enrollment_id)
        if not paid:
            continue
        student = db.get(Student, paid.student_id)
        try:
            notification_service.enqueue_typed_text(
                db=db,
                message_type="payment",
                text=_render_payment_notice(paid, student),
            )
        except Exception:
            # 通知链路异常不影响批量交费主流程。
            pass

    return results
