from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.schemas import ApiResponse

router = APIRouter()


@router.get("/health", response_model=ApiResponse)
def health(db: Session = Depends(get_db)) -> ApiResponse:
    try:
        db.execute(select(1))
    except SQLAlchemyError:
        return ApiResponse(code=50000, message="database disconnected", data=None)
    return ApiResponse(data={"status": "ok"})


@router.get(f"{config.api_prefix}/status", response_model=ApiResponse)
def status(db: Session = Depends(get_db)) -> ApiResponse:
    db_status = "ok"
    overall_status = "ok"

    try:
        db.execute(select(1))
    except SQLAlchemyError:
        db_status = "fail"
        overall_status = "fail"

    return ApiResponse(
        data={
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "postgresql": db_status,
                "self": "ok",
            },
        }
    )
