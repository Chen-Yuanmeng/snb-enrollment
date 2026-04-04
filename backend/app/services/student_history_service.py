from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.grade_mapping import history_grade_candidates
from app.errors import raise_biz_error
from app.models import StudentHistory
from app.schemas import StudentHistoryCreateRequest, StudentHistoryOut
from app.services.shared_service import log_operation


def search_for_renewal(db: Session, name: str, grade: str) -> list[dict[str, Any]]:
    trimmed_name = name.strip()
    trimmed_grade = grade.strip()
    if not trimmed_name or not trimmed_grade:
        raise_biz_error(40001, "老生姓名和年级不能为空")
    grade_candidates = history_grade_candidates(trimmed_grade)

    stmt = (
        select(StudentHistory)
        .where(
            StudentHistory.name == trimmed_name,
            StudentHistory.grade.in_(grade_candidates),
            StudentHistory.can_renew_discount.is_(True),
        )
        .order_by(desc(StudentHistory.id))
        .limit(30)
    )
    rows = db.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
        }
        for row in rows
    ]


def search_for_referral(db: Session, name: str) -> list[dict[str, Any]]:
    trimmed_name = name.strip()
    if not trimmed_name:
        raise_biz_error(40001, "老生姓名不能为空")

    stmt = (
        select(StudentHistory)
        .where(StudentHistory.name.ilike(f"%{trimmed_name}%"))
        .order_by(desc(StudentHistory.id))
        .limit(30)
    )
    rows = db.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
        }
        for row in rows
    ]


def list_students_history(
    db: Session,
    keyword: str | None = None,
    grade: str | None = None,
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
) -> dict[str, Any]:
    normalized_page = page if isinstance(page, int) else 1
    normalized_page_size = page_size if isinstance(page_size, int) else 20
    normalized_limit = limit if isinstance(limit, int) else None

    effective_page_size = normalized_limit if normalized_limit is not None else normalized_page_size
    effective_page = 1 if normalized_limit is not None else normalized_page

    filters = []
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            filters.append(
                or_(
                    StudentHistory.name.ilike(f"%{trimmed}%"),
                    StudentHistory.grade.ilike(f"%{trimmed}%"),
                    StudentHistory.phone_suffix.ilike(f"%{trimmed}%"),
                )
            )
    if grade:
        candidates = history_grade_candidates(grade)
        filters.append(StudentHistory.grade.in_(candidates))

    data_stmt = select(StudentHistory)
    count_stmt = select(func.count()).select_from(StudentHistory)
    if filters:
        data_stmt = data_stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(
        data_stmt
        .order_by(desc(StudentHistory.id))
        .offset((effective_page - 1) * effective_page_size)
        .limit(effective_page_size)
    ).all()

    data = [StudentHistoryOut.model_validate(row).model_dump() for row in rows]
    return {
        "data": data,
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
    }


def create_student_history(db: Session, payload: StudentHistoryCreateRequest) -> dict[str, Any]:
    if not payload.name:
        raise_biz_error(40001, "老生姓名不能为空")

    row = StudentHistory(
        name=payload.name,
        grade=payload.grade,
        phone_suffix=payload.phone_suffix,
        can_renew_discount=payload.can_renew_discount,
        note=payload.note,
    )
    db.add(row)
    db.flush()

    log_operation(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_student_history",
        target_type="student_history",
        target_id=row.id,
        result_status="success",
        request_summary={
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
            "can_renew_discount": row.can_renew_discount,
        },
    )

    db.commit()
    return StudentHistoryOut.model_validate(row).model_dump()
