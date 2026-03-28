from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.errors import raise_biz_error
from app.pricing_engine import build_quote
from app.schemas import QuoteCalculateRequest
from app.services.shared_service import inject_auto_discounts


def calculate_quote(db: Session, payload: QuoteCalculateRequest) -> dict:
    try:
        effective_payload = inject_auto_discounts(db, payload)
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))
    except HTTPException:
        raise
    return quote.model_dump()
