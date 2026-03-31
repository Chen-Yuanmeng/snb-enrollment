from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.constants import (
    ACCOMMODATION_STATUS_CANCELLED,
    ACCOMMODATION_STATUS_CONFIRMED,
    ACCOMMODATION_STATUS_GENERATED,
)
from app.core.datetime_utils import utcnow_naive
from app.errors import raise_biz_error
from app.models import AccommodationEnrollment, Enrollment, Student
from app.rules_loader import get_accommodation_rule
from app.schemas import AccommodationCreateRequest, AccommodationOut, AccommodationStatusUpdateRequest
from app.services import notification_service
from app.services.shared_service import log_operation


def _get_room_type_display(room_type: str, other_room_type_name: str | None) -> str:
    if room_type == "其他房型" and other_room_type_name:
        return f"其他房型({other_room_type_name})"
    return room_type


def _normalize_page(page: int, page_size: int, limit: int | None) -> tuple[int, int]:
    normalized_page = page if isinstance(page, int) else 1
    normalized_page_size = page_size if isinstance(page_size, int) else 20
    normalized_limit = limit if isinstance(limit, int) else None
    effective_page_size = normalized_limit if normalized_limit is not None else normalized_page_size
    effective_page = 1 if normalized_limit is not None else normalized_page
    return effective_page, effective_page_size


def _validate_and_price(payload: AccommodationCreateRequest) -> dict[str, Any]:
    rule = get_accommodation_rule()

    hotels = {str(item).strip() for item in rule.get("hotels", []) if str(item).strip()}
    if payload.hotel not in hotels:
        raise_biz_error(40001, "酒店选项非法")

    room_items = [item for item in rule.get("room_types", []) if isinstance(item, dict)]
    room_type_map: dict[str, dict[str, Any]] = {}
    for item in room_items:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        room_type_map[name] = item
    room_conf = room_type_map.get(payload.room_type)
    if not room_conf:
        raise_biz_error(40001, "房型选项非法")

    duration_map: dict[int, str] = {}
    for item in rule.get("durations", []):
        if not isinstance(item, dict):
            continue
        days = item.get("days")
        label = str(item.get("label", "")).strip()
        if isinstance(days, int) and days > 0 and label:
            duration_map[days] = label
    duration_label = duration_map.get(payload.duration_days)
    if not duration_label:
        raise_biz_error(40001, "时长选项非法")

    genders = {str(item).strip() for item in rule.get("genders", []) if str(item).strip()}
    if payload.gender not in genders:
        raise_biz_error(40001, "性别选项非法")

    requires_custom_price = bool(room_conf.get("requires_custom_price", False))
    if requires_custom_price:
        if not payload.other_room_type_name:
            raise_biz_error(40001, "其他房型必须填写房型名称")
        if payload.nightly_price is None or payload.nightly_price <= 0:
            raise_biz_error(40001, "其他房型必须填写大于0的每晚价格")
        nightly_price = float(payload.nightly_price)
    else:
        nightly_price_map = rule.get("nightly_prices", {})
        if not isinstance(nightly_price_map, dict):
            raise_biz_error(50000, "住宿规则 nightly_prices 配置错误", status_code=500)
        hotel_prices = nightly_price_map.get(payload.hotel, {})
        if not isinstance(hotel_prices, dict):
            raise_biz_error(40001, "所选酒店未配置房型价格")
        nightly = hotel_prices.get(payload.room_type)
        if nightly is None:
            raise_biz_error(40001, "所选酒店未配置该房型价格")
        nightly_price = float(nightly)
        if nightly_price <= 0:
            raise_biz_error(50000, "住宿规则价格非法", status_code=500)

    total_price = round(nightly_price * payload.duration_days, 2)
    return {
        "duration_label": duration_label,
        "nightly_price": nightly_price,
        "total_price": total_price,
        "room_type_display": _get_room_type_display(payload.room_type, payload.other_room_type_name),
    }


def _render_quote_text(payload: AccommodationCreateRequest, context: dict[str, Any]) -> str:
    return "\n".join(
        [
            "【住宿报价】",
            f"关联课程报价单: #{payload.related_enrollment_id}",
            f"学生: {context.get('student_name', '-')}",
            f"手机号: {context.get('student_phone', '-')}",
            f"酒店: {payload.hotel}",
            f"房型: {context.get('room_type_display', payload.room_type)}",
            f"时长: {context.get('duration_label', '')}",
            f"性别: {payload.gender}",
            f"总价: ¥{context.get('total_price', 0):.2f}",
            f"备注: {payload.note or '-'}",
            "状态: 已生成",
        ]
    )


def _render_status_change_notice(
    student_name: str,
    related_enrollment_id: int,
    hotel: str,
    room_type_display: str,
    duration_label: str,
    gender: str,
    total_price: float,
    target_status: str,
) -> str:
    lines = [
        f"学生姓名: {student_name}",
        f"关联课程报价单号: {related_enrollment_id}",
        f"{hotel} | {room_type_display}",
        f"{duration_label} | {gender}",
    ]
    if target_status == ACCOMMODATION_STATUS_CONFIRMED:
        lines = ["【住宿 - 交费通知】"] + lines
        lines.append(f"住宿费 ¥{total_price:.2f} 已交")
        return "\n".join(lines)
    elif target_status == ACCOMMODATION_STATUS_CANCELLED:
        lines = ["【住宿 - 取消通知】"] + lines
        lines.append(f"住宿费之前已交 ¥{total_price:.2f} 需退款")
        return "\n".join(lines)
    else:
        return ""


def create_accommodation(db: Session, payload: AccommodationCreateRequest) -> dict[str, Any]:
    related = db.get(Enrollment, payload.related_enrollment_id)
    if not related:
        raise_biz_error(40401, "关联报价单不存在", status_code=404)

    student = db.get(Student, related.student_id)
    price_context = _validate_and_price(payload)
    quote_text = _render_quote_text(
        payload,
        {
            **price_context,
            "student_name": student.name if student else "-",
            "student_phone": student.phone if student else "-",
        },
    )

    row = AccommodationEnrollment(
        related_enrollment_id=payload.related_enrollment_id,
        hotel=payload.hotel,
        room_type=payload.room_type,
        other_room_type_name=payload.other_room_type_name,
        duration_days=payload.duration_days,
        duration_label=price_context["duration_label"],
        gender=payload.gender,
        nightly_price=price_context["nightly_price"],
        total_price=price_context["total_price"],
        quote_text=quote_text,
        status=ACCOMMODATION_STATUS_GENERATED,
        operator_name=payload.operator_name,
        source=payload.source,
        note=payload.note,
    )
    db.add(row)
    db.flush()

    log_operation(
        db=db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_accommodation",
        target_type="accommodation",
        target_id=row.id,
        result_status="success",
        request_summary={
            "related_enrollment_id": payload.related_enrollment_id,
            "hotel": payload.hotel,
            "room_type": payload.room_type,
            "duration_days": payload.duration_days,
            "gender": payload.gender,
        },
    )

    db.commit()
    return {
        "accommodation_id": row.id,
        "status": row.status,
        "quote_text": row.quote_text,
        "total_price": float(row.total_price),
        "nightly_price": float(row.nightly_price),
    }


def list_accommodations(
    db: Session,
    status: str | None = None,
    hotel: str | None = None,
    room_type: str | None = None,
    gender: str | None = None,
    source: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
) -> dict[str, Any]:
    effective_page, effective_page_size = _normalize_page(page, page_size, limit)

    data_stmt = (
        select(
            AccommodationEnrollment,
            Student.name.label("student_name"),
            Student.phone.label("student_phone"),
            Enrollment.grade.label("grade"),
            Enrollment.status.label("related_enrollment_status"),
        )
        .join(Enrollment, AccommodationEnrollment.related_enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
    )
    count_stmt = (
        select(func.count())
        .select_from(AccommodationEnrollment)
        .join(Enrollment, AccommodationEnrollment.related_enrollment_id == Enrollment.id)
        .join(Student, Enrollment.student_id == Student.id)
    )

    filters = []
    if status:
        filters.append(AccommodationEnrollment.status == status)
    if hotel:
        filters.append(AccommodationEnrollment.hotel == hotel)
    if room_type:
        filters.append(AccommodationEnrollment.room_type == room_type)
    if gender:
        filters.append(AccommodationEnrollment.gender == gender)
    if source:
        filters.append(AccommodationEnrollment.source == source)
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            if trimmed.isdigit():
                filters.append(
                    or_(
                        Student.name.ilike(f"%{trimmed}%"),
                        AccommodationEnrollment.id == int(trimmed),
                        AccommodationEnrollment.related_enrollment_id == int(trimmed),
                    )
                )
            else:
                filters.append(Student.name.ilike(f"%{trimmed}%"))

    if filters:
        data_stmt = data_stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.execute(
        data_stmt
        .order_by(desc(AccommodationEnrollment.id))
        .offset((effective_page - 1) * effective_page_size)
        .limit(effective_page_size)
    ).all()

    data: list[dict[str, Any]] = []
    for row, student_name, student_phone, grade, related_enrollment_status in rows:
        item = AccommodationOut.model_validate(row).model_dump()
        item["student_name"] = student_name or ""
        item["student_phone"] = student_phone or ""
        item["grade"] = grade or ""
        item["related_enrollment_status"] = related_enrollment_status or ""
        item["nightly_price"] = float(row.nightly_price)
        item["total_price"] = float(row.total_price)
        item["room_type_display"] = _get_room_type_display(row.room_type, row.other_room_type_name)
        data.append(item)

    return {
        "data": data,
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
    }


def update_accommodation_status(
    db: Session, accommodation_id: int, payload: AccommodationStatusUpdateRequest
) -> dict[str, Any]:
    row = db.get(AccommodationEnrollment, accommodation_id)
    if row is None:
        raise_biz_error(40401, "住宿记录不存在", status_code=404)

    current = row.status
    target = payload.status

    transition_allowed = (
        (current == ACCOMMODATION_STATUS_GENERATED and target in {ACCOMMODATION_STATUS_CONFIRMED, ACCOMMODATION_STATUS_CANCELLED})
        or (current == ACCOMMODATION_STATUS_CONFIRMED and target == ACCOMMODATION_STATUS_CANCELLED)
    )
    if not transition_allowed:
        raise_biz_error(40005, "状态流转非法")

    row.status = target
    row.updated_at = utcnow_naive()
    row.note = payload.note or row.note

    log_operation(
        db=db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="update_accommodation_status",
        target_type="accommodation",
        target_id=row.id,
        result_status="success",
        request_summary={
            "from_status": current,
            "to_status": target,
        },
    )
    db.commit()

    should_send_notice = (
        (current == ACCOMMODATION_STATUS_GENERATED and target == ACCOMMODATION_STATUS_CONFIRMED)
        or (current == ACCOMMODATION_STATUS_CONFIRMED and target == ACCOMMODATION_STATUS_CANCELLED)
    )
    if should_send_notice:
        related = db.get(Enrollment, row.related_enrollment_id)
        student_name = "-"
        if related:
            student = db.get(Student, related.student_id)
            if student and student.name:
                student_name = student.name

        try:
            notification_service.enqueue_typed_text(
                db=db,
                message_type="accommodation",
                text=_render_status_change_notice(
                    student_name=student_name,
                    related_enrollment_id=row.related_enrollment_id,
                    hotel=row.hotel,
                    room_type_display=_get_room_type_display(row.room_type, row.other_room_type_name),
                    duration_label=row.duration_label,
                    gender=row.gender,
                    total_price=float(row.total_price),
                    target_status=target,
                ),
            )
        except Exception:
            # 通知链路异常不影响状态流转主流程。
            pass

    return {"accommodation_id": row.id, "status": row.status}


def get_accommodation_stats(db: Session) -> dict[str, Any]:
    stmt = (
        select(
            AccommodationEnrollment.hotel,
            AccommodationEnrollment.room_type,
            AccommodationEnrollment.other_room_type_name,
            AccommodationEnrollment.gender,
            func.count().label("student_count"),
        )
        .where(AccommodationEnrollment.status == ACCOMMODATION_STATUS_CONFIRMED)
        .group_by(
            AccommodationEnrollment.hotel,
            AccommodationEnrollment.room_type,
            AccommodationEnrollment.other_room_type_name,
            AccommodationEnrollment.gender,
        )
        .order_by(
            AccommodationEnrollment.hotel.asc(),
            AccommodationEnrollment.room_type.asc(),
            AccommodationEnrollment.other_room_type_name.asc(),
            AccommodationEnrollment.gender.asc(),
        )
    )
    rows = db.execute(stmt).all()
    data = []
    total_confirmed = 0
    for hotel, room_type, other_room_type_name, gender, student_count in rows:
        count = int(student_count or 0)
        total_confirmed += count
        data.append(
            {
                "hotel": hotel,
                "room_type": room_type,
                "room_type_display": _get_room_type_display(room_type, other_room_type_name),
                "gender": gender,
                "student_count": count,
            }
        )
    return {"rows": data, "total_confirmed": total_confirmed}


def search_related_enrollments(
    db: Session,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
) -> dict[str, Any]:
    effective_page, effective_page_size = _normalize_page(page, page_size, limit)
    data_stmt = select(Enrollment, Student.name.label("student_name"), Student.phone.label("student_phone")).join(
        Student, Enrollment.student_id == Student.id
    )
    count_stmt = select(func.count()).select_from(Enrollment).join(Student, Enrollment.student_id == Student.id)

    filters = []
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

    data = []
    for enrollment, student_name, student_phone in rows:
        data.append(
            {
                "enrollment_id": enrollment.id,
                "student_name": student_name or "",
                "student_phone": student_phone or "",
                "grade": enrollment.grade,
                "status": enrollment.status,
                "final_price": float(enrollment.final_price),
                "source": enrollment.source,
                "created_at": enrollment.created_at,
            }
        )
    return {
        "data": data,
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
    }
