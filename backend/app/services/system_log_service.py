import re
import subprocess
from datetime import datetime
from typing import Any

from app.errors import raise_biz_error

DEFAULT_SYSTEMD_UNIT = "snb-enrollment.service"
MAX_PAGE_SIZE = 100
MAX_FETCH_LINES = 10000

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
