from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import config
from app.core.validation import ensure_operator, ensure_source
from app.database import get_db
from app.schemas import ApiResponse, NotificationSendRequest
from app.services import notification_service
from app.services.message_queue_service import dump_task

router = APIRouter()


@router.post(f"{config.api_prefix}/notifications/send", response_model=ApiResponse)
def send_typed_message(payload: NotificationSendRequest, db: Session = Depends(get_db)) -> ApiResponse:
    ensure_operator(payload.operator_name)
    ensure_source(payload.source)

    task = notification_service.enqueue_typed_text(db=db, message_type=payload.type, text=payload.text)
    return ApiResponse(data=dump_task(task))
