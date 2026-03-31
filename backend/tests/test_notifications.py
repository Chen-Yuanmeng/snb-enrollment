from app.models import MessageTask
from app.services import notification_service
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def test_enqueue_typed_text_creates_task(monkeypatch):
    db = _make_session()
    try:
        monkeypatch.setattr(
            notification_service.wecom_config,
            "type_webhook_env_mapping_raw",
            '{"quotation":"WECOM_WEBHOOK_QUOTATION"}',
        )
        monkeypatch.setenv(
            "WECOM_WEBHOOK_QUOTATION",
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        )
        monkeypatch.setattr(notification_service, "enqueue_task", lambda task_id: None)

        task = notification_service.enqueue_typed_text(db, "quotation", "hello")
        assert task.id > 0
        assert task.webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        assert task.status == "pending"

        row = db.scalar(select(MessageTask).where(MessageTask.id == task.id))
        assert row is not None
        assert row.message_type == "quotation"
    finally:
        db.close()


def test_enqueue_accommodation_type_creates_task(monkeypatch):
    db = _make_session()
    try:
        monkeypatch.setattr(
            notification_service.wecom_config,
            "type_webhook_env_mapping_raw",
            '{"accommodation":"WECOM_WEBHOOK_ACCOMMODATION"}',
        )
        monkeypatch.setenv(
            "WECOM_WEBHOOK_ACCOMMODATION",
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=accommodation",
        )
        monkeypatch.setattr(notification_service, "enqueue_task", lambda task_id: None)

        task = notification_service.enqueue_typed_text(db, "accommodation", "hello")
        assert task.id > 0
        assert task.webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=accommodation"
        assert task.status == "pending"
    finally:
        db.close()


def test_enqueue_typed_text_requires_mapping():
    db = _make_session()
    try:
        try:
            notification_service.enqueue_typed_text(db, "missing_type", "hello")
            assert False, "should fail when mapping missing"
        except ValueError as exc:
            assert "不支持的通知类型" in str(exc)
    finally:
        db.close()
