import json
import ipaddress
import re
import subprocess
from datetime import datetime, timedelta
from urllib import parse, request
from typing import Any

from app.errors import raise_biz_error

DEFAULT_SYSTEMD_UNIT = "snb-enrollment.service"
MAX_PAGE_SIZE = 100
MAX_FETCH_LINES = 10000
IP_LOOKUP_URL = "https://ip.zxinc.org/api.php"
IP_LOOKUP_USER_AGENT = "snb-enrollment-flow-control/1.0"

ACCESS_LOG_PATTERN = re.compile(
    r'(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+):\d+\s+-\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})'
)


def _normalize_timestamp(value: str) -> str:
    token = value.strip()
    if not token:
        return token
    if re.search(r"[+-]\d{4}$", token):
        return f"{token[:-5]}{token[-5:-2]}:{token[-2:]}"
    return token


def _parse_timestamp_from_journal_line(line: str) -> str | None:
    parts = line.split(" ", 1)
    if not parts:
        return None
    token = parts[0].strip()
    if "T" not in token:
        return None
    try:
        parsed = datetime.fromisoformat(_normalize_timestamp(token))
    except ValueError:
        return None
    return parsed.isoformat()


def _extract_access_log_fields(line: str) -> dict[str, Any] | None:
    match = ACCESS_LOG_PATTERN.search(line)
    if not match:
        return None

    status_code = int(match.group("status"))
    timestamp = _parse_timestamp_from_journal_line(line)

    return {
        "timestamp": timestamp,
        "ip": match.group("ip"),
        "method": match.group("method"),
        "path": match.group("path"),
        "status_code": status_code,
        "raw": line,
    }


def _build_journalctl_command(
    *,
    since: str | None,
    until: str | None,
    max_lines: int,
) -> list[str]:
    command = [
        "journalctl",
        "-u",
        DEFAULT_SYSTEMD_UNIT,
        "--no-pager",
        "-o",
        "short-iso",
        "-n",
        str(max_lines),
    ]
    if since:
        command.extend(["--since", since])
    if until:
        command.extend(["--until", until])
    return command


def _fetch_journal_lines(*, since: str | None, until: str | None, max_lines: int) -> list[str]:
    command = _build_journalctl_command(since=since, until=until, max_lines=max_lines)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )
    except FileNotFoundError:
        raise_biz_error(50000, "当前环境缺少 journalctl，无法读取 systemd 日志", status_code=500)
    except subprocess.TimeoutExpired:
        raise_biz_error(50000, "读取 systemd 日志超时，请缩小时间范围重试", status_code=500)

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise_biz_error(50000, f"读取 systemd 日志失败: {stderr or '未知错误'}", status_code=500)

    output = completed.stdout or ""
    return [line for line in output.splitlines() if line.strip()]


def _match_filters(
    item: dict[str, Any],
    *,
    ip: str | None,
    method: str | None,
    path_keyword: str | None,
    status_code: int | None,
) -> bool:
    if ip and item["ip"] != ip:
        return False
    if method and item["method"] != method.upper():
        return False
    if path_keyword and path_keyword not in item["path"]:
        return False
    if status_code is not None and item["status_code"] != status_code:
        return False
    return True


def list_system_access_logs(
    *,
    since: str | None = None,
    until: str | None = None,
    ip: str | None = None,
    method: str | None = None,
    path_keyword: str | None = None,
    status_code: int | None = None,
    page: int = 1,
    page_size: int = 20,
    max_lines: int = 2000,
) -> dict[str, Any]:
    normalized_page = max(1, page)
    normalized_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    normalized_max_lines = max(200, min(max_lines, MAX_FETCH_LINES))

    lines = _fetch_journal_lines(since=since, until=until, max_lines=normalized_max_lines)

    access_entries: list[dict[str, Any]] = []
    for line in lines:
        parsed = _extract_access_log_fields(line)
        if not parsed:
            continue
        if not _match_filters(
            parsed,
            ip=ip,
            method=method,
            path_keyword=path_keyword,
            status_code=status_code,
        ):
            continue
        access_entries.append(parsed)

    access_entries.reverse()
    total = len(access_entries)

    start = (normalized_page - 1) * normalized_page_size
    end = start + normalized_page_size
    items = access_entries[start:end]

    return {
        "items": items,
        "total": total,
        "page": normalized_page,
        "page_size": normalized_page_size,
    }


def _normalize_ip(value: str) -> str:
    token = (value or "").strip()
    if not token:
        raise_biz_error(40001, "ip 不能为空")
    try:
        return str(ipaddress.ip_address(token))
    except ValueError:
        raise_biz_error(40001, "ip 格式不合法")


def _fetch_ip_location(ip: str) -> dict[str, Any] | None:
    query = parse.urlencode({"type": "json", "ip": ip})
    url = f"{IP_LOOKUP_URL}?{query}"
    req = request.Request(
        url,
        headers={
            "User-Agent": IP_LOOKUP_USER_AGENT,
            "Accept": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=4) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if payload.get("code") != 0:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    ip_info = data.get("ip") if isinstance(data.get("ip"), dict) else {}
    return {
        "query": ip_info.get("query") or ip,
        "location": data.get("location"),
        "country": data.get("country"),
        "local": data.get("local"),
    }


def _safe_parse_iso_datetime(value: str | None) -> datetime | None:
    token = (value or "").strip()
    if not token:
        return None
    try:
        return datetime.fromisoformat(token)
    except ValueError:
        return None


def summarize_system_access_logs_by_ip(
    *,
    ip: str,
    since: str | None = None,
    until: str | None = None,
    max_lines: int = MAX_FETCH_LINES,
) -> dict[str, Any]:
    normalized_ip = _normalize_ip(ip)
    normalized_max_lines = max(200, min(max_lines, MAX_FETCH_LINES))

    lines = _fetch_journal_lines(since=since, until=until, max_lines=normalized_max_lines)

    count = 0
    for line in lines:
        parsed = _extract_access_log_fields(line)
        if not parsed:
            continue
        if parsed["ip"] == normalized_ip:
            count += 1

    return {
        "ip": normalized_ip,
        "since": since,
        "until": until,
        "count": count,
        "line_scan_count": len(lines),
        "line_scan_limit": normalized_max_lines,
        "truncated": len(lines) >= normalized_max_lines,
        "location": _fetch_ip_location(normalized_ip),
    }


def summarize_system_access_logs_by_ip_hourly(
    *,
    ip: str,
    last_hours: int = 24,
    max_lines: int = MAX_FETCH_LINES,
) -> dict[str, Any]:
    normalized_ip = _normalize_ip(ip)
    normalized_last_hours = max(1, min(last_hours, 168))
    normalized_max_lines = max(200, min(max_lines, MAX_FETCH_LINES))

    now = datetime.now().astimezone()
    end_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start_time = end_time - timedelta(hours=normalized_last_hours)

    since = start_time.strftime("%Y-%m-%d %H:%M:%S")
    until = now.strftime("%Y-%m-%d %H:%M:%S")
    lines = _fetch_journal_lines(since=since, until=until, max_lines=normalized_max_lines)

    bucket_counts: dict[str, int] = {}
    for index in range(normalized_last_hours):
        bucket_start = start_time + timedelta(hours=index)
        key = bucket_start.strftime("%Y-%m-%d %H:00:00")
        bucket_counts[key] = 0

    for line in lines:
        parsed = _extract_access_log_fields(line)
        if not parsed or parsed["ip"] != normalized_ip:
            continue

        parsed_time = _safe_parse_iso_datetime(parsed.get("timestamp"))
        if parsed_time is None:
            continue
        parsed_local = parsed_time.astimezone(now.tzinfo)
        bucket_start = parsed_local.replace(minute=0, second=0, microsecond=0)
        key = bucket_start.strftime("%Y-%m-%d %H:00:00")
        if key in bucket_counts:
            bucket_counts[key] += 1

    buckets = [{"hour": hour, "count": count} for hour, count in bucket_counts.items()]

    return {
        "ip": normalized_ip,
        "last_hours": normalized_last_hours,
        "since": since,
        "until": until,
        "total": sum(item["count"] for item in buckets),
        "buckets": buckets,
        "line_scan_count": len(lines),
        "line_scan_limit": normalized_max_lines,
        "truncated": len(lines) >= normalized_max_lines,
    }
