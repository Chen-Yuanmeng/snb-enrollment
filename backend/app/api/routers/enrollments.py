from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.services import enrollment_service
from app.schemas import ApiResponse, BatchPayRequest, EnrollmentCreateRequest, EnrollmentOut, PayRequest

router = APIRouter()


@router.post(f"{config.api_prefix}/enrollments", response_model=ApiResponse)
def create_enrollment(payload: EnrollmentCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    data = enrollment_service.create_enrollment(db, payload)
    return ApiResponse(data=data)


@router.get(f"{config.api_prefix}/enrollments", response_model=ApiResponse)
def list_enrollments(
    status: str | None = None,
    student_id: int | None = None,
    grade: str | None = None,
    valid: bool | None = None,
    source: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    latest_only: bool = True,
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = enrollment_service.list_enrollments(
        db=db,
        status=status,
        student_id=student_id,
        grade=grade,
        valid=valid,
        source=source,
        keyword=keyword,
        page=page,
        page_size=page_size,
        limit=limit,
        latest_only=latest_only,
    )
    return ApiResponse(**result)


@router.get(f"{config.api_prefix}/enrollments/{{enrollment_id}}", response_model=ApiResponse)
def get_enrollment(enrollment_id: int, db: Session = Depends(get_db)) -> ApiResponse:
    return ApiResponse(data=enrollment_service.get_enrollment(db, enrollment_id))


@router.post(f"{config.api_prefix}/enrollments/{{enrollment_id}}/pay", response_model=ApiResponse)
def pay_enrollment(enrollment_id: int, payload: PayRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    data = enrollment_service.pay_enrollment(db, enrollment_id, payload)
    return ApiResponse(data=data)


@router.post(f"{config.api_prefix}/enrollments/pay-batch", response_model=ApiResponse)
def pay_batch(payload: BatchPayRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=enrollment_service.pay_batch(db, payload))
