import time

import redis

from app.integrations.wecom.config import wecom_config


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(wecom_config.redis_url, decode_responses=True)


def enqueue_task(task_id: int) -> None:
    client = _redis_client()
    client.lpush(wecom_config.queue_key, str(task_id))


def pop_task_id(timeout_seconds: int | None = None) -> int | None:
    client = _redis_client()
    timeout = timeout_seconds if timeout_seconds is not None else wecom_config.worker_pop_timeout_seconds
    item = client.brpop(wecom_config.queue_key, timeout=timeout)
    if not item:
        return None
    _, value = item
    return int(value)


def schedule_retry(task_id: int, run_at_epoch_seconds: float) -> None:
    client = _redis_client()
    client.zadd(wecom_config.retry_zset_key, {str(task_id): run_at_epoch_seconds})


def move_due_retries(limit: int = 50) -> int:
    client = _redis_client()
    now = time.time()
    task_ids = client.zrangebyscore(wecom_config.retry_zset_key, min=0, max=now, start=0, num=limit)
    if not task_ids:
        return 0
    pipe = client.pipeline()
    for tid in task_ids:
        pipe.zrem(wecom_config.retry_zset_key, tid)
        pipe.lpush(wecom_config.queue_key, tid)
    pipe.execute()
    return len(task_ids)
