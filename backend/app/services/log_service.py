from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import OperationLog


def list_logs(
    db: Session,
    operator_name: str | None = None,
    source: str | None = None,
    action_type: str | None = None,
    target_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, 200))

    stmt = select(OperationLog)
    if operator_name:
        stmt = stmt.where(OperationLog.operator_name == operator_name)
    if source:
        stmt = stmt.where(OperationLog.source == source)
    if action_type:
        stmt = stmt.where(OperationLog.action_type == action_type)
    if target_type:
        stmt = stmt.where(OperationLog.target_type == target_type)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.scalar(total_stmt) or 0)

    stmt = stmt.order_by(desc(OperationLog.id)).offset((normalized_page - 1) * normalized_page_size).limit(normalized_page_size)
    rows = db.scalars(stmt).all()

    return {
        "items": [
        {
            "id": row.id,
            "operator_name": row.operator_name,
            "source": row.source,
            "action_type": row.action_type,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "result_status": row.result_status,
            "message": row.message,
            "created_at": row.created_at,
        }
        for row in rows
        ],
        "total": total,
        "page": normalized_page,
        "page_size": normalized_page_size,
    }
