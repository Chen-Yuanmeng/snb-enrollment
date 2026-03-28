from sqlalchemy.orm import Session

from app.constants import VALID_NOTIFICATION_TYPES
from app.integrations.wecom.config import wecom_config
from app.models import MessageTask
from app.services import message_queue_service
from app.services.redis_queue_service import enqueue_task


def enqueue_typed_text(db: Session, message_type: str, text: str) -> MessageTask:
    if message_type not in VALID_NOTIFICATION_TYPES:
        raise ValueError(f"不支持的通知类型: {message_type}")

    webhook_url = wecom_config.resolve_webhook(message_type)
    if not webhook_url:
        raise ValueError(f"未找到 type={message_type} 对应的 webhook 配置")

    task = message_queue_service.create_task(
        db=db,
        message_type=message_type,
        text=text,
        webhook_url=webhook_url,
    )
    db.commit()

    try:
        enqueue_task(task.id)
    except Exception:
        # 不阻塞主业务；任务仍保存在数据库，可由补偿任务重新入队。
        pass

    return task


def max_retries() -> int:
    return max(0, wecom_config.max_retries)
