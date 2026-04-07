import json
from datetime import timedelta, datetime

import pytest
from fastapi import HTTPException

from app.services import system_log_service


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_summarize_system_access_logs_by_ip(monkeypatch):
    lines = [
        '2026-04-07T10:00:00+0800 host app[1]: 1.2.3.4:123 - "GET /api/v1/logs HTTP/1.1" 200',
        '2026-04-07T10:00:01+0800 host app[1]: 5.6.7.8:234 - "POST /api/v1/enrollments HTTP/1.1" 200',
        '2026-04-07T10:00:02+0800 host app[1]: 1.2.3.4:345 - "GET /api/v1/system-access-logs HTTP/1.1" 200',
    ]

    monkeypatch.setattr(system_log_service, "_fetch_journal_lines", lambda **_: lines)
    monkeypatch.setattr(
        system_log_service.request,
        "urlopen",
        lambda req, timeout=4: _FakeHttpResponse(
            {
                "code": 0,
                "data": {
                    "ip": {"query": "1.2.3.4", "start": "", "end": ""},
                    "location": "中国-北京",
                    "country": "中国",
                    "local": "联通",
                },
            }
        ),
    )

    result = system_log_service.summarize_system_access_logs_by_ip(
        ip="1.2.3.4",
        since="2026-04-07 00:00:00",
        until="2026-04-07 23:59:59",
        max_lines=10000,
    )

    assert result["ip"] == "1.2.3.4"
    assert result["count"] == 2
    assert result["truncated"] is False
    assert result["location"]["location"] == "中国-北京"


def test_summarize_system_access_logs_by_ip_rejects_invalid_ip():
    with pytest.raises(HTTPException) as exc:
        system_log_service.summarize_system_access_logs_by_ip(ip="not-an-ip")

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == 40001


def test_summarize_system_access_logs_by_ip_hourly(monkeypatch):
    now = datetime.now().astimezone()
    t1 = (now - timedelta(minutes=70)).strftime("%Y-%m-%dT%H:%M:%S%z")
    t2 = (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S%z")
    t3 = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S%z")

    lines = [
        f'{t1} host app[1]: 1.2.3.4:123 - "GET /api/v1/logs HTTP/1.1" 200',
        f'{t2} host app[1]: 1.2.3.4:234 - "GET /api/v1/system-access-logs HTTP/1.1" 200',
        f'{t3} host app[1]: 5.6.7.8:234 - "GET /api/v1/enrollments HTTP/1.1" 200',
    ]

    monkeypatch.setattr(system_log_service, "_fetch_journal_lines", lambda **_: lines)

    result = system_log_service.summarize_system_access_logs_by_ip_hourly(
        ip="1.2.3.4",
        last_hours=2,
        max_lines=10000,
    )

    assert result["ip"] == "1.2.3.4"
    assert result["last_hours"] == 2
    assert result["total"] == 2
    assert len(result["buckets"]) == 2
    assert result["truncated"] is False
