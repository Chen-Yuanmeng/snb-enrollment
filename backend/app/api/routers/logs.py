from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.schemas import ApiResponse
from app.services import log_service

router = APIRouter()


@router.get(f"{config.api_prefix}/logs", response_model=ApiResponse)
def list_logs(
    operator_name: str | None = None,
    source: str | None = None,
    action_type: str | None = None,
    target_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> ApiResponse:
    data = log_service.list_logs(
        db=db,
        operator_name=operator_name,
        source=source,
        action_type=action_type,
        target_type=target_type,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=data)
