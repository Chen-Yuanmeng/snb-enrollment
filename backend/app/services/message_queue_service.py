import hashlib
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    MESSAGE_STATUS_DEAD,
    MESSAGE_STATUS_FAILED,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSING,
    MESSAGE_STATUS_SUCCEEDED,
)
from app.core.datetime_utils import utcnow_naive
from app.models import MessageTask


def build_idempotency_key(message_type: str, text: str, webhook_url: str) -> str:
    raw = f"{message_type}:{webhook_url}:{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_task(
    db: Session,
    message_type: str,
    text: str,
    webhook_url: str,
    idempotency_key: str | None = None,
) -> MessageTask:
    dedupe_key = idempotency_key or build_idempotency_key(message_type, text, webhook_url)
    existing = db.scalar(select(MessageTask).where(MessageTask.idempotency_key == dedupe_key))
    if existing:
        return existing

    row = MessageTask(
        message_type=message_type,
        webhook_url=webhook_url,
        text=text,
        payload={"type": message_type, "text": text, "webhook_url": webhook_url},
        idempotency_key=dedupe_key,
        status=MESSAGE_STATUS_PENDING,
        retry_count=0,
    )
    db.add(row)
    db.flush()
    return row


def mark_processing(db: Session, task: MessageTask) -> None:
    task.status = MESSAGE_STATUS_PROCESSING
    task.updated_at = utcnow_naive()
    db.flush()


def mark_succeeded(db: Session, task: MessageTask, remote_msg_id: str | None = None) -> None:
    task.status = MESSAGE_STATUS_SUCCEEDED
    task.remote_msg_id = remote_msg_id
    task.executed_at = utcnow_naive()
    task.updated_at = utcnow_naive()
    db.flush()


def mark_failed_and_plan_retry(db: Session, task: MessageTask, error_message: str, max_retries: int) -> None:
    now = utcnow_naive()
    task.retry_count += 1
    task.last_error = error_message
    task.updated_at = now

    chain = task.error_chain or []
    chain.append({"at": now.isoformat(), "message": error_message})
    task.error_chain = chain

    if task.retry_count > max_retries:
        task.status = MESSAGE_STATUS_DEAD
        task.next_retry_at = None
        task.executed_at = now
    else:
        wait_seconds = 2 ** task.retry_count
        task.status = MESSAGE_STATUS_FAILED
        task.next_retry_at = now + timedelta(seconds=wait_seconds)
    db.flush()


def mark_pending_for_retry(db: Session, task: MessageTask) -> None:
    task.status = MESSAGE_STATUS_PENDING
    task.updated_at = utcnow_naive()
    db.flush()


def dump_task(task: MessageTask) -> dict:
    return {
        "id": task.id,
        "message_type": task.message_type,
        "webhook_url": task.webhook_url,
        "text": task.text,
        "status": task.status,
        "retry_count": task.retry_count,
        "next_retry_at": task.next_retry_at,
        "last_error": task.last_error,
        "remote_msg_id": task.remote_msg_id,
        "payload": json.loads(json.dumps(task.payload or {})),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
