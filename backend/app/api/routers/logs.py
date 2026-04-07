from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.schemas import ApiResponse
from app.services import log_service, system_log_service

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
    payload = log_service.list_logs(
        db=db,
        operator_name=operator_name,
        source=source,
        action_type=action_type,
        target_type=target_type,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(
        data=payload["items"],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
    )


@router.get(f"{config.api_prefix}/system-access-logs", response_model=ApiResponse)
def list_system_access_logs(
    since: str | None = None,
    until: str | None = None,
    ip: str | None = None,
    method: str | None = None,
    path_keyword: str | None = None,
    status_code: int | None = None,
    page: int = 1,
    page_size: int = 20,
    max_lines: int = 2000,
) -> ApiResponse:
    data = system_log_service.list_system_access_logs(
        since=since,
        until=until,
        ip=ip,
        method=method,
        path_keyword=path_keyword,
        status_code=status_code,
        page=page,
        page_size=page_size,
        max_lines=max_lines,
    )
    return ApiResponse(
        data=data["items"],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
    )


@router.get(f"{config.api_prefix}/system-access-logs/ip-summary", response_model=ApiResponse)
def get_system_access_ip_summary(
    ip: str,
    since: str | None = None,
    until: str | None = None,
    max_lines: int = 10000,
) -> ApiResponse:
    data = system_log_service.summarize_system_access_logs_by_ip(
        ip=ip,
        since=since,
        until=until,
        max_lines=max_lines,
    )
    return ApiResponse(data=data)


@router.get(f"{config.api_prefix}/system-access-logs/ip-hourly", response_model=ApiResponse)
def get_system_access_ip_hourly(
    ip: str,
    last_hours: int = 24,
    max_lines: int = 10000,
) -> ApiResponse:
    data = system_log_service.summarize_system_access_logs_by_ip_hourly(
        ip=ip,
        last_hours=last_hours,
        max_lines=max_lines,
    )
    return ApiResponse(data=data)
