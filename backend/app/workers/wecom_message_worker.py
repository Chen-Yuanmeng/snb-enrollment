import time

from sqlalchemy import select

from app.constants import MESSAGE_STATUS_DEAD, MESSAGE_STATUS_PENDING
from app.database import SessionLocal
from app.integrations.wecom import WeComClient, wecom_config
from app.models import MessageTask
from app.services import message_queue_service, notification_service
from app.services.redis_queue_service import move_due_retries, pop_task_id, schedule_retry


def process_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.get(MessageTask, task_id)
        if not task:
            return
        if task.status not in {MESSAGE_STATUS_PENDING, "failed", "processing"}:
            return

        message_queue_service.mark_processing(db, task)
        db.commit()

        client = WeComClient()
        client.send_text(task.webhook_url, task.text)

        message_queue_service.mark_succeeded(db, task, remote_msg_id=None)
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.get(MessageTask, task_id)
        if not task:
            return
        message_queue_service.mark_failed_and_plan_retry(
            db,
            task,
            error_message=str(exc),
            max_retries=notification_service.max_retries(),
        )
        db.commit()
        if task.status != MESSAGE_STATUS_DEAD and task.next_retry_at is not None:
            schedule_retry(task.id, task.next_retry_at.timestamp())
    finally:
        db.close()


def refill_due_pending_tasks(limit: int = 200) -> int:
    db = SessionLocal()
    moved = 0
    try:
        rows = db.scalars(
            select(MessageTask)
            .where(
                MessageTask.status == "failed",
                MessageTask.next_retry_at.is_not(None),
            )
            .limit(limit)
        ).all()
        now = time.time()
        for row in rows:
            if row.next_retry_at and row.next_retry_at.timestamp() <= now:
                message_queue_service.mark_pending_for_retry(db, row)
                schedule_retry(row.id, 0)
                moved += 1
        if moved:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return moved


def run_forever() -> None:
    while True:
        move_due_retries()
        refill_due_pending_tasks()

        task_id = pop_task_id(timeout_seconds=wecom_config.worker_pop_timeout_seconds)
        if task_id is None:
            continue
        process_task(task_id)


def main() -> None:
    try:
        run_forever()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
