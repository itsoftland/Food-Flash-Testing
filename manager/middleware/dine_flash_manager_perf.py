"""
Dine Flash: middleware timing for outlet-manager API requests.

Measures wall-clock time from first middleware entry through response, which
includes JWT auth, ORM, and view work. View-level segments are merged from
request._dine_flash_perf when the handler finishes.

Loaded only when PROJECT_NAME == "dine_flash" (see caller_on/settings.py).
"""

from __future__ import annotations

import logging
import time
import uuid

from django.utils import timezone

from manager.utils.dine_flash_request_perf import (
    TRACE_ATTR,
    apply_perf_response_headers,
    should_trace_manager_request,
)

logger = logging.getLogger("manager.dine_flash_perf")


class DineFlashManagerPerfMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not should_trace_manager_request(request):
            return self.get_response(request)

        started_mono = time.perf_counter()
        started_wall = timezone.now().isoformat()
        trace_id = uuid.uuid4().hex[:12]

        trace = {
            "trace_id": trace_id,
            "started_at_wall": started_wall,
            "started_mono": started_mono,
            "path": request.path,
            "method": request.method,
            "segments": {},
        }
        setattr(request, TRACE_ATTR, trace)

        logger.info(
            "[dine_flash_perf] phase=request_in trace_id=%s started_at=%s method=%s path=%s",
            trace_id,
            started_wall,
            request.method,
            request.path,
        )

        response = self.get_response(request)

        total_ms = (time.perf_counter() - started_mono) * 1000
        trace["total_ms"] = total_ms
        handler_ms = trace.get("handler_ms")
        segments = trace.get("segments") or {}

        user = getattr(request, "user", None)
        user_hint = ""
        if user is not None and getattr(user, "is_authenticated", False):
            user_hint = f" user_id={user.pk} user={getattr(user, 'username', '')}"

        segment_bits = []
        for key, value in sorted(segments.items()):
            if isinstance(value, (int, float)):
                segment_bits.append(f"{key}_ms={int(value)}")
            else:
                segment_bits.append(f"{key}={value}")

        overhead_ms = "-"
        if handler_ms is not None:
            overhead_ms = str(max(0, int(total_ms - handler_ms)))

        logger.info(
            "[dine_flash_perf] phase=request_out trace_id=%s started_at=%s method=%s path=%s "
            "status=%s total_ms=%s handler_ms=%s overhead_ms=%s%s %s",
            trace_id,
            started_wall,
            request.method,
            request.path,
            getattr(response, "status_code", "?"),
            int(total_ms),
            int(handler_ms) if handler_ms is not None else "-",
            overhead_ms,
            user_hint,
            " ".join(segment_bits),
        )

        if total_ms >= 800:
            logger.warning(
                "[dine_flash_perf] phase=slow_request trace_id=%s path=%s total_ms=%s",
                trace_id,
                request.path,
                int(total_ms),
            )

        apply_perf_response_headers(request, response)
        return response
