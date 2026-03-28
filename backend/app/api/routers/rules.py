from fastapi import APIRouter

from app.config import config
from app.schemas import ApiResponse
from app.services import rule_service

router = APIRouter()


@router.get(f"{config.api_prefix}/operators", response_model=ApiResponse)
def get_operators() -> ApiResponse:
    return ApiResponse(data=rule_service.list_operators())


@router.get(f"{config.api_prefix}/sources", response_model=ApiResponse)
def get_sources() -> ApiResponse:
    return ApiResponse(data=rule_service.list_sources())


@router.get(f"{config.api_prefix}/rules/meta", response_model=ApiResponse)
def get_rules_meta() -> ApiResponse:
    return ApiResponse(data=rule_service.get_rules_meta())


@router.get(f"{config.api_prefix}/rules/grade/{{grade}}", response_model=ApiResponse)
def get_rule_by_grade(grade: str) -> ApiResponse:
    return ApiResponse(data=rule_service.get_rule_by_grade(grade))
