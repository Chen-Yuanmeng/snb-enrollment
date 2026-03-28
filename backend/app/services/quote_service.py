from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.errors import raise_biz_error
from app.pricing_engine import build_quote
from app.schemas import QuoteCalculateRequest
from app.services.shared_service import inject_auto_discounts
from app.services import notification_service


def calculate_quote(db: Session, payload: QuoteCalculateRequest) -> dict:
    try:
        effective_payload = inject_auto_discounts(db, payload)
        quote = build_quote(effective_payload)
        try:
            notification_service.enqueue_typed_text(
                db=db,
                message_type="quotation",
                text=quote.quote_text,
            )
        except Exception:
            # 通知链路异常不影响报价主流程。
            pass
    except ValueError as exc:
        raise_biz_error(40001, str(exc))
    except HTTPException:
        raise
    return quote.model_dump()
