"""
Dine Flash outlet-manager API performance tracing.

Used by middleware (wall-clock, auth + view + DB) and by manager views (handler
segments). Logs always include trace_id and ISO started_at so server logs can be
correlated with phone stopwatch / Charles / app timestamps.

Scope: PROJECT_NAME == "dine_flash" only.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("manager.dine_flash_perf")

TRACE_ATTR = "_dine_flash_perf"


def is_dine_flash_project() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"


def should_trace_manager_request(request) -> bool:
    """True for Dine Flash manager REST API calls."""
    if not is_dine_flash_project():
        return False
    path = (getattr(request, "path", None) or "").lower()
    return "/manager/api/" in path


def ensure_request_trace(request) -> Optional[Dict[str, Any]]:
    """
    Return the active trace dict, creating one if middleware did not (e.g. tests).
    """
    if not should_trace_manager_request(request):
        return None

    trace = getattr(request, TRACE_ATTR, None)
    if trace is not None:
        return trace

    trace = {
        "trace_id": uuid.uuid4().hex[:12],
        "started_at_wall": timezone.now().isoformat(),
        "started_mono": time.perf_counter(),
        "path": getattr(request, "path", ""),
        "method": getattr(request, "method", "?"),
        "segments": {},
    }
    setattr(request, TRACE_ATTR, trace)
    return trace


def merge_trace_segments(request, **segments: Any) -> None:
    trace = ensure_request_trace(request)
    if trace is None:
        return
    trace.setdefault("segments", {}).update(
        {k: v for k, v in segments.items() if v is not None}
    )


def log_trace_phase(request, phase: str, endpoint: Optional[str] = None, **extra: Any) -> None:
    trace = getattr(request, TRACE_ATTR, None)
    if trace is None:
        return

    user = getattr(request, "user", None)
    user_id = None
    username = None
    if user is not None and getattr(user, "is_authenticated", False):
        user_id = getattr(user, "pk", None)
        username = getattr(user, "username", None)

    parts = [
        f"phase={phase}",
        f"trace_id={trace['trace_id']}",
        f"started_at={trace['started_at_wall']}",
        f"method={trace.get('method', '?')}",
        f"path={trace.get('path', '')}",
    ]
    if endpoint:
        parts.append(f"endpoint={endpoint}")
    if user_id is not None:
        parts.append(f"user_id={user_id}")
    if username:
        parts.append(f"user={username}")
    for key, value in extra.items():
        if value is not None:
            parts.append(f"{key}={value}")

    logger.info("[dine_flash_perf] %s", " ".join(parts))


def format_segments_for_header(segments: Dict[str, Any]) -> str:
    """Build Server-Timing style fragment for response headers."""
    chunks = []
    for key, value in segments.items():
        if key in {"count", "cache", "cache_status", "status"}:
            continue
        if isinstance(value, (int, float)):
            chunks.append(f"{key};dur={float(value):.1f}")
    return ", ".join(chunks)


def record_handler_timing(request, endpoint: str, handler_started: float, **segments: Any) -> None:
    """Log handler-only duration and merge segments for middleware response_out."""
    handler_ms = (time.perf_counter() - handler_started) * 1000
    trace = ensure_request_trace(request)
    if trace is not None:
        trace["handler_ms"] = handler_ms
    merge_trace_segments(request, **segments)
    log_trace_phase(
        request,
        "handler_done",
        endpoint=endpoint,
        handler_ms=int(handler_ms),
        **{k: v for k, v in segments.items() if not isinstance(v, float)},
    )


def apply_perf_response_headers(request, response) -> None:
    trace = getattr(request, TRACE_ATTR, None)
    if trace is None:
        return

    total_ms = trace.get("total_ms")
    handler_ms = trace.get("handler_ms")
    segments = trace.get("segments") or {}

    response["X-DineFlash-Trace-Id"] = trace["trace_id"]
    response["X-DineFlash-Request-Started-At"] = trace["started_at_wall"]
    if total_ms is not None:
        response["X-DineFlash-Total-Ms"] = str(int(total_ms))
    if handler_ms is not None:
        response["X-DineFlash-Handler-Ms"] = str(int(handler_ms))

    timing = format_segments_for_header(segments)
    if total_ms is not None:
        timing = f"total;dur={float(total_ms):.1f}" + (f", {timing}" if timing else "")
    if timing:
        response["Server-Timing"] = timing
