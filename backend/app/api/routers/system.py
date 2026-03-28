from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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
