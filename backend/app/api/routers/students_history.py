from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.schemas import ApiResponse, StudentHistoryCreateRequest
from app.services import student_history_service

router = APIRouter()


@router.get(f"{config.api_prefix}/students-history/search/renewal", response_model=ApiResponse)
def search_students_history_for_renewal(
    name: str = Query(...),
    grade: str = Query(...),
    db: Session = Depends(get_db),
) -> ApiResponse:
    return ApiResponse(data=student_history_service.search_for_renewal(db, name, grade))


@router.get(f"{config.api_prefix}/students-history/search/referral", response_model=ApiResponse)
def search_students_history_for_referral(
    name: str = Query(...),
    db: Session = Depends(get_db),
) -> ApiResponse:
    return ApiResponse(data=student_history_service.search_for_referral(db, name))


@router.get(f"{config.api_prefix}/students-history", response_model=ApiResponse)
def list_students_history(
    keyword: str | None = None,
    grade: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = student_history_service.list_students_history(
        db=db,
        keyword=keyword,
        grade=grade,
        page=page,
        page_size=page_size,
        limit=limit,
    )
    return ApiResponse(**result)


@router.post(f"{config.api_prefix}/students-history", response_model=ApiResponse)
def create_student_history(payload: StudentHistoryCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=student_history_service.create_student_history(db, payload))
