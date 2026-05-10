from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Deque

_REQUEST_TIMESTAMPS: Deque[datetime] = deque()
_RECENT_REQUEST_LOGS: Deque[dict] = deque(maxlen=120)
_LOCK = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trim_requests_locked(window_seconds: int) -> None:
    cutoff = _now().timestamp() - window_seconds
    while _REQUEST_TIMESTAMPS and _REQUEST_TIMESTAMPS[0].timestamp() < cutoff:
        _REQUEST_TIMESTAMPS.popleft()


def record_request_event(method: str, path: str, status_code: int, duration_ms: float, query: str = "") -> None:
    timestamp = _now()
    query_suffix = f"?{query}" if query else ""
    message = f"[{timestamp.strftime('%H:%M:%S')}] {method} {path}{query_suffix} {status_code} {duration_ms:.1f}ms"

    with _LOCK:
        _REQUEST_TIMESTAMPS.append(timestamp)
        _RECENT_REQUEST_LOGS.append(
            {
                "timestamp": timestamp,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 1),
                "message": message,
            }
        )
        _trim_requests_locked(window_seconds=60)


def get_request_volume(window_seconds: int = 60) -> dict:
    with _LOCK:
        _trim_requests_locked(window_seconds)
        request_count = len(_REQUEST_TIMESTAMPS)

    requests_per_second = round(request_count / window_seconds, 1) if window_seconds > 0 else 0
    return {
        "request_count": request_count,
        "requests_per_second": requests_per_second,
        "unit": "count",
        "window_seconds": window_seconds,
        "timestamp": _now(),
        "error": None,
    }


def _read_meminfo_kb() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as meminfo_file:
            for line in meminfo_file:
                if ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                parts = raw_value.strip().split()
                if not parts:
                    continue
                try:
                    values[key] = int(parts[0])
                except ValueError:
                    continue
    except OSError:
        return {}
    return values


def get_memory_usage() -> dict:
    meminfo = _read_meminfo_kb()
    total_kb = meminfo.get("MemTotal")
    if not total_kb:
        return {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
            "percent_used": None,
            "unit": "bytes",
            "timestamp": _now(),
            "error": "Unable to read /proc/meminfo",
        }

    available_kb = meminfo.get(
        "MemAvailable",
        meminfo.get("MemFree", 0)
        + meminfo.get("Buffers", 0)
        + meminfo.get("Cached", 0)
        + meminfo.get("SReclaimable", 0)
        - meminfo.get("Shmem", 0),
    )

    used_kb = max(0, total_kb - available_kb)
    percent_used = round((used_kb / total_kb) * 100, 1) if total_kb else None

    return {
        "total_bytes": total_kb * 1024,
        "used_bytes": used_kb * 1024,
        "available_bytes": max(0, available_kb) * 1024,
        "percent_used": percent_used,
        "unit": "bytes",
        "timestamp": _now(),
        "error": None,
    }


def get_recent_request_logs(limit: int = 10) -> dict:
    with _LOCK:
        entries = list(_RECENT_REQUEST_LOGS)[-limit:]

    return {
        "entries": entries,
        "updated_at": _now(),
    }


def get_request_traffic_history(bucket_count: int = 10, window_seconds: int = 60) -> dict:
    bucket_count = max(1, bucket_count)
    window_seconds = max(1, window_seconds)
    bucket_seconds = window_seconds / bucket_count

    with _LOCK:
        _trim_requests_locked(window_seconds)
        timestamps = list(_REQUEST_TIMESTAMPS)

    if not timestamps:
        return {
            "window_seconds": window_seconds,
            "bucket_seconds": bucket_seconds,
            "samples": [
                {
                    "label": f"-{window_seconds - int(index * bucket_seconds)}s",
                    "request_count": 0,
                    "requests_per_second": 0,
                    "timestamp": _now(),
                }
                for index in range(bucket_count)
            ],
            "updated_at": _now(),
        }

    oldest_timestamp = _now().timestamp() - window_seconds
    samples = []

    for index in range(bucket_count):
        bucket_start = oldest_timestamp + (index * bucket_seconds)
        bucket_end = bucket_start + bucket_seconds
        count = len([timestamp for timestamp in timestamps if bucket_start <= timestamp.timestamp() < bucket_end])
        samples.append(
            {
                "label": f"-{int(window_seconds - (index + 1) * bucket_seconds)}s",
                "request_count": count,
                "requests_per_second": round(count / bucket_seconds, 1),
                "timestamp": datetime.fromtimestamp(bucket_end, tz=timezone.utc),
            }
        )

    return {
        "window_seconds": window_seconds,
        "bucket_seconds": bucket_seconds,
        "samples": samples,
        "updated_at": _now(),
    }


def _tail_file(path: str, limit: int) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as log_file:
            lines = log_file.readlines()
    except OSError:
        return []

    return [line.rstrip("\n") for line in lines[-limit:] if line.strip()]


def _parse_host_log_timestamp(line: str) -> datetime:
    try:
        return datetime.strptime(f"{_now().year} {line[:15]}", "%Y %b %d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return _now()


def get_ec2_logs(limit: int = 12) -> dict:
    candidate_paths = [
        "/host-logs/messages",
        "/host-logs/syslog",
        "/host-logs/auth.log",
        "/host-logs/cloud-init.log",
        "/host-logs/cloud-init-output.log",
        "/var/log/messages",
        "/var/log/syslog",
        "/var/log/auth.log",
        "/var/log/cloud-init.log",
        "/var/log/cloud-init-output.log",
    ]

    entries: list[dict] = []
    lines_per_file = max(2, limit // 2)

    for path in candidate_paths:
        entries.extend(
            {
                "source": "host",
                "message": line,
                "timestamp": _parse_host_log_timestamp(line),
            }
            for line in _tail_file(path, lines_per_file)
        )

    with _LOCK:
        recent_request_entries = list(_RECENT_REQUEST_LOGS)[-lines_per_file:]

    entries.extend(
        {
            "source": "app",
            "message": entry["message"],
            "timestamp": entry["timestamp"],
        }
        for entry in recent_request_entries
    )

    entries = sorted(entries, key=lambda entry: entry["timestamp"] or _now(), reverse=True)[:limit]
    return {
        "entries": entries,
        "updated_at": _now(),
    }