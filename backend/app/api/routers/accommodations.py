from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.schemas import AccommodationCreateRequest, AccommodationStatusUpdateRequest, ApiResponse
from app.services import accommodation_service

router = APIRouter()


@router.post(f"{config.api_prefix}/accommodations", response_model=ApiResponse)
def create_accommodation(
    payload: AccommodationCreateRequest, db: Session = Depends(get_db)
) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=accommodation_service.create_accommodation(db, payload))


@router.get(f"{config.api_prefix}/accommodations", response_model=ApiResponse)
def list_accommodations(
    status: str | None = None,
    hotel: str | None = None,
    room_type: str | None = None,
    gender: str | None = None,
    source: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = accommodation_service.list_accommodations(
        db=db,
        status=status,
        hotel=hotel,
        room_type=room_type,
        gender=gender,
        source=source,
        keyword=keyword,
        page=page,
        page_size=page_size,
        limit=limit,
    )
    return ApiResponse(**result)


@router.post(f"{config.api_prefix}/accommodations/{{accommodation_id}}/status", response_model=ApiResponse)
def update_accommodation_status(
    accommodation_id: int,
    payload: AccommodationStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(
        data=accommodation_service.update_accommodation_status(db, accommodation_id, payload)
    )


@router.get(f"{config.api_prefix}/accommodations/stats", response_model=ApiResponse)
def get_accommodation_stats(db: Session = Depends(get_db)) -> ApiResponse:
    return ApiResponse(data=accommodation_service.get_accommodation_stats(db))


@router.get(f"{config.api_prefix}/accommodations/related-enrollments/search", response_model=ApiResponse)
def search_related_enrollments(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ApiResponse:
    result = accommodation_service.search_related_enrollments(
        db=db,
        keyword=keyword,
        page=page,
        page_size=page_size,
        limit=limit,
    )
    return ApiResponse(**result)
