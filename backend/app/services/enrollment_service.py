import re
from datetime import UTC, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.constants import ENROLLMENT_STATS_INCLUDED_STATUSES, STATUS_CANCELLED, STATUS_PAID, STATUS_QUOTED
from app.core.datetime_utils import utcnow_naive
from app.errors import raise_biz_error
from app.models import Enrollment, Student, StudentHistory
from app.pricing_engine import build_fingerprint, build_quote
from app.schemas import BatchPayRequest, EnrollmentCancelRequest, EnrollmentCreateRequest, EnrollmentOut, PayRequest
from app.services import notification_service
from app.services.shared_service import get_or_create_student, inject_auto_discounts, log_operation

PAID_AT_DISPLAY_YEAR = 2026
PAID_AT_TZ = ZoneInfo("Asia/Shanghai")
PAID_AT_INPUT_PATTERN = re.compile(r"^(?P<month>\d{2})\.(?P<day>\d{2})\s+(?P<hour>\d{2})(?P<minute>\d{2})$")


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


def _parse_paid_at_input(value: str) -> datetime:
    raw = value.strip()
    matched = PAID_AT_INPUT_PATTERN.fullmatch(raw)
    if not matched:
        raise_biz_error(40001, "请输入 mm.dd hhmm 格式，例如 04.29 1530")

    month = int(matched.group("month"))
    day = int(matched.group("day"))
    hour = int(matched.group("hour"))
    minute = int(matched.group("minute"))

    try:
        local_dt = datetime(PAID_AT_DISPLAY_YEAR, month, day, hour, minute, tzinfo=PAID_AT_TZ)
    except ValueError:
        raise_biz_error(40001, "输入的日期时间无效")

    return local_dt.astimezone(UTC).replace(tzinfo=None)


def _ensure_student_history_after_payment(db: Session, enrollment: Enrollment) -> None:
    student = db.get(Student, enrollment.student_id)
    if student is None:
        return

    student_name = (student.name or "").strip()
    if not student_name:
        return

    grade = (enrollment.grade or "").strip() or None
    phone_suffix = (student.phone or "").strip() or None
    existed = db.scalar(
        select(StudentHistory.id)
        .where(
            StudentHistory.name == student_name,
            StudentHistory.grade == grade,
            StudentHistory.phone_suffix == phone_suffix,
        )
        .limit(1)
    )
    if existed is not None:
        return

    db.add(
        StudentHistory(
            name=student_name,
            grade=grade,
            phone_suffix=phone_suffix,
            can_renew_discount=False,
            note="系统自动补录：确认缴费",
        )
    )
    db.flush()


def _bucket_subject_modes(enrollment: Enrollment) -> tuple[set[str], set[str]]:
    subjects = {
        str(subject).strip()
        for subject in (enrollment.class_subjects or [])
        if str(subject).strip()
    }
    if not subjects:
        return set(), set()

    mode = (enrollment.class_mode or "").strip()
    if mode == "线下":
        return subjects, set()
    if mode == "线上":
        return set(), subjects

    details = enrollment.mode_details if isinstance(enrollment.mode_details, dict) else {}
    offline_subjects = {
        str(subject).strip()
        for subject in details.get("offline_subjects", [])
        if str(subject).strip()
    }
    online_subjects = {
        str(subject).strip()
        for subject in details.get("online_subjects", [])
        if str(subject).strip()
    }
    offline_subjects &= subjects
    online_subjects &= subjects

    missing = subjects - offline_subjects - online_subjects
    if missing:
        # 混合上课方式下兜底按线上统计，避免丢失科目计数。
        online_subjects |= missing

    return offline_subjects, online_subjects


def get_enrollment_stats(db: Session) -> dict[str, Any]:
    child = aliased(Enrollment)
    has_newer = exists(select(1).where(child.previous_enrollment_id == Enrollment.id))
    rows = db.scalars(
        select(Enrollment).where(
            Enrollment.valid.is_(True),
            Enrollment.status.in_(ENROLLMENT_STATS_INCLUDED_STATUSES),
            ~has_newer,
        )
    ).all()

    counter: dict[tuple[str, str], dict[str, int]] = {}
    total_units = 0
    total_offline = 0
    total_online = 0

    for enrollment in rows:
        grade = (enrollment.grade or "").strip() or "-"
        offline_subjects, online_subjects = _bucket_subject_modes(enrollment)

        for subject in sorted(offline_subjects):
            key = (grade, subject)
            bucket = counter.setdefault(key, {"offline_count": 0, "online_count": 0})
            bucket["offline_count"] += 1
            total_units += 1
            total_offline += 1

        for subject in sorted(online_subjects):
            key = (grade, subject)
            bucket = counter.setdefault(key, {"offline_count": 0, "online_count": 0})
            bucket["online_count"] += 1
            total_units += 1
            total_online += 1

    stats_rows = []
    for (grade, subject), item in sorted(counter.items(), key=lambda entry: (entry[0][0], entry[0][1])):
        offline_count = int(item["offline_count"])
        online_count = int(item["online_count"])
        stats_rows.append(
            {
                "grade": grade,
                "subject": subject,
                "offline_count": offline_count,
                "online_count": online_count,
                "total_count": offline_count + online_count,
            }
        )

    return {
        "rows": stats_rows,
        "summary": {
            "total_rows": len(rows),
            "total_enrollment_subject_units": total_units,
            "total_offline": total_offline,
            "total_online": total_online,
        },
    }


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
    latest_only: bool = True,
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

    if latest_only:
        child = aliased(Enrollment)
        has_newer = exists(select(1).where(child.previous_enrollment_id == Enrollment.id))
        data_stmt = data_stmt.where(~has_newer)
        count_stmt = count_stmt.where(~has_newer)

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
        "paid_at": row.paid_at,
        "created_at": row.created_at,
    }


def pay_enrollment(db: Session, enrollment_id: int, payload: PayRequest) -> dict[str, Any]:
    row = db.get(Enrollment, enrollment_id)
    if row is None:
        raise_biz_error(40401, "记录不存在", status_code=404)
    row = cast(Enrollment, row)
    if row.status != STATUS_QUOTED:
        raise_biz_error(40005, "状态流转非法")

    row.paid_at = _parse_paid_at_input(payload.paid_at)
    row.status = STATUS_PAID
    row.updated_at = utcnow_naive()
    row.note = payload.note or row.note
    _ensure_student_history_after_payment(db, row)

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


def cancel_enrollment(db: Session, enrollment_id: int, payload: EnrollmentCancelRequest) -> dict[str, Any]:
    row = db.get(Enrollment, enrollment_id)
    if row is None:
        raise_biz_error(40401, "记录不存在", status_code=404)
    row = cast(Enrollment, row)
    if row.status != STATUS_QUOTED:
        raise_biz_error(40005, "状态流转非法")

    row.status = STATUS_CANCELLED
    row.updated_at = utcnow_naive()
    row.note = payload.note or row.note

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="cancel_enrollment",
        target_type="enrollment",
        target_id=row.id,
        result_status="success",
    )
    db.commit()
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
        _ensure_student_history_after_payment(db, row)
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
