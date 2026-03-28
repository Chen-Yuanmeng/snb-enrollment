from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.schemas import ApiResponse
from app.services import student_service

router = APIRouter()


@router.get(f"{config.api_prefix}/students/search", response_model=ApiResponse)
def search_students(keyword: str = Query(...), db: Session = Depends(get_db)) -> ApiResponse:
    return ApiResponse(data=student_service.search_students(db, keyword))
