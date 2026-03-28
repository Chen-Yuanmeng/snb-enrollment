from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.grade_mapping import archive_student_grade
from app.models import OperationLog, Student
from app.schemas import EnrollmentCreateRequest, QuoteCalculateRequest


def get_or_create_student(db: Session, req: EnrollmentCreateRequest | QuoteCalculateRequest) -> Student:
    stmt = select(Student).where(Student.phone == req.student_info.phone)
    student = db.scalar(stmt)
    if student:
        return student

    student = Student(
        name=req.student_info.name,
        phone=req.student_info.phone,
        gender=req.student_info.gender,
        school=req.student_info.school,
        grade=archive_student_grade(req.grade),
        note=req.student_info.note,
    )
    db.add(student)
    db.flush()
    return student


def inject_auto_discounts(
    db: Session,
    payload: EnrollmentCreateRequest | QuoteCalculateRequest,
) -> EnrollmentCreateRequest | QuoteCalculateRequest:
    del db
    # 自动优惠的最终判定放在前端，后端仅按前端提交结果进行校验与计价。
    return payload


def log_operation(
    db: Session,
    operator_name: str,
    source: str,
    action_type: str,
    target_type: str,
    target_id: int | None,
    result_status: str,
    message: str | None = None,
    request_summary: dict | None = None,
) -> None:
    log = OperationLog(
        operator_name=operator_name,
        source=source,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        result_status=result_status,
        message=message,
        request_summary=request_summary,
    )
    db.add(log)
