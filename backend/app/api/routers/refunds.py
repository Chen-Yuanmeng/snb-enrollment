from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.services import refund_service
from app.schemas import ApiResponse, RefundCreateRequest, RefundPreviewRequest

router = APIRouter()


@router.post(f"{config.api_prefix}/refunds/preview", response_model=ApiResponse)
def preview_refund(payload: RefundPreviewRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=refund_service.preview_refund(db, payload))


@router.post(f"{config.api_prefix}/refunds", response_model=ApiResponse)
def create_refund(payload: RefundCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=refund_service.create_refund(db, payload))
