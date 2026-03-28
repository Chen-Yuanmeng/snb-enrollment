import json
import os

from pydantic import BaseModel, field_validator


class WeComConfig(BaseModel):
    redis_url: str = os.getenv("WECOM_REDIS_URL", "redis://127.0.0.1:6379/0")
    queue_key: str = os.getenv("WECOM_QUEUE_KEY", "wecom:message_tasks")
    retry_zset_key: str = os.getenv("WECOM_RETRY_ZSET_KEY", "wecom:message_tasks:retry")

    max_retries: int = int(os.getenv("WECOM_MAX_RETRIES", "3"))
    retry_backoff_seconds: int = int(os.getenv("WECOM_RETRY_BACKOFF_SECONDS", "2"))
    worker_pop_timeout_seconds: int = int(os.getenv("WECOM_WORKER_POP_TIMEOUT_SECONDS", "5"))

    type_webhook_env_mapping_raw: str = os.getenv("WECOM_TYPE_WEBHOOK_ENV_MAPPING", "{}")

    @field_validator("type_webhook_env_mapping_raw")
    @classmethod
    def validate_mapping_json(cls, value: str) -> str:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("WECOM_TYPE_WEBHOOK_ENV_MAPPING 必须是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("WECOM_TYPE_WEBHOOK_ENV_MAPPING 必须是对象 JSON")
        return value

    def type_webhook_env_mapping(self) -> dict[str, str]:
        data = json.loads(self.type_webhook_env_mapping_raw)
        return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}

    def resolve_webhook(self, message_type: str) -> str | None:
        mapping = self.type_webhook_env_mapping()
        env_name = mapping.get(message_type)
        if not env_name:
            return None
        value = os.getenv(env_name, "").strip()
        return value or None


wecom_config = WeComConfig()
