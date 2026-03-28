from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    # Keep DB values as naive datetime in UTC while avoiding deprecated utcnow().
    return datetime.now(UTC).replace(tzinfo=None)
