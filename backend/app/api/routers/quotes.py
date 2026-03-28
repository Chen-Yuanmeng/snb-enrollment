from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.schemas import ApiResponse, QuoteCalculateRequest
from app.services import quote_service

router = APIRouter()


@router.post(f"{config.api_prefix}/quotes/calculate", response_model=ApiResponse)
def calculate_quote(payload: QuoteCalculateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)
    return ApiResponse(data=quote_service.calculate_quote(db, payload))
