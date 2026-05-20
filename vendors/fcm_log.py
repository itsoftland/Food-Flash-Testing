"""Dine Flash FCM audit log (written to fcm.log under the daily log folder)."""
from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_AUDIT_LOGGER_NAMES = ("dine_flash.fcm", "vendors.dine_flash_tv_fcm")
_FALLBACK_HANDLER: logging.FileHandler | None = None
_LOGGING_CONFIGURED = False


def _payload_str(payload: Mapping[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str)


def _anchor_log_dir(log_dir: Path) -> Path:
    """On IIS/Windows, LOG_DIR is often relative to the process cwd — anchor to BASE_DIR."""
    if log_dir.is_absolute():
        return log_dir
    try:
        from django.conf import settings

        base_dir = Path(getattr(settings, "BASE_DIR", "") or "")
        if base_dir:
            return (base_dir / log_dir).resolve()
    except Exception:
        pass
    return log_dir.resolve()


def _resolve_fcm_log_path() -> Path | None:
    """Match caller_on/settings.py daily log folder layout (same folder as managers.log)."""
    try:
        from django.conf import settings

        log_dir = getattr(settings, "LOG_DIR", None)
        if log_dir:
            return _anchor_log_dir(Path(log_dir)) / "fcm.log"
    except Exception:
        pass

    try:
        from django.conf import settings

        project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        external = Path(getattr(settings, "EXTERNAL_LOG_DIR", "") or "")
        base_dir = Path(getattr(settings, "BASE_DIR", "") or "")

        if external:
            if project == "airline_flash":
                base = external / "airline_flash_logs"
            elif project == "dine_flash":
                base = external / "dine_flash_logs"
            else:
                base = external / "foodflash_logs"
        elif base_dir:
            if project == "airline_flash":
                base = base_dir / "airline_flash_logs"
            elif project == "dine_flash":
                base = base_dir / "dine_flash_logs"
            else:
                base = base_dir / "foodflash_logs"
        else:
            return None

        today = datetime.now()
        log_dir = base / str(today.year) / today.strftime("%B") / f"{today.day:02d}"
        return log_dir / "fcm.log"
    except Exception:
        return None


def _get_fallback_handler() -> logging.FileHandler | None:
    global _FALLBACK_HANDLER
    if _FALLBACK_HANDLER is not None:
        return _FALLBACK_HANDLER

    path = _resolve_fcm_log_path()
    if not path:
        return None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "[{asctime}] {levelname} {name} {message}",
                style="{",
            )
        )
        _FALLBACK_HANDLER = handler
        return handler
    except Exception:
        return None


def _logger_has_fcm_file_handler(logger: logging.Logger) -> bool:
    for handler in logger.handlers:
        if not isinstance(handler, logging.FileHandler):
            continue
        try:
            if str(handler.baseFilename).endswith("fcm.log"):
                return True
        except Exception:
            continue
    return False


def _ensure_audit_loggers() -> list[logging.Logger]:
    """
    Ensure FCM audit records reach fcm.log even if LOGGING dict omits dine_flash.fcm
    (misconfigured workers would otherwise drop messages with propagate=False).
    """
    global _LOGGING_CONFIGURED
    if not _LOGGING_CONFIGURED:
        try:
            from django.conf import settings

            if hasattr(settings, "LOGGING"):
                logging.config.dictConfig(settings.LOGGING)
        except Exception:
            pass
        _LOGGING_CONFIGURED = True

    fallback = _get_fallback_handler()
    loggers: list[logging.Logger] = []
    for name in _AUDIT_LOGGER_NAMES:
        lg = logging.getLogger(name)
        if fallback and not _logger_has_fcm_file_handler(lg):
            lg.addHandler(fallback)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        loggers.append(lg)
    return loggers


def _flush() -> None:
    seen: set[int] = set()
    for name in _AUDIT_LOGGER_NAMES:
        for handler in logging.getLogger(name).handlers:
            hid = id(handler)
            if hid in seen:
                continue
            seen.add(hid)
            flush = getattr(handler, "flush", None)
            if callable(flush):
                flush()


def log_fcm_send_success(
    *,
    source: str,
    token: str,
    payload: Mapping[str, Any] | str,
    vendor_id: Optional[int] = None,
    label: str = "",
) -> None:
    """Record a successful FCM delivery with the registration token and data payload."""
    message = (
        f"[fcm_success] source={source} vendor_id={vendor_id if vendor_id is not None else ''} "
        f"label={label} token={token} payload={_payload_str(payload)}"
    )
    for lg in _ensure_audit_loggers():
        lg.info(message)
    _flush()


def log_fcm_token_registered(
    *,
    action: str,
    mac_address: str,
    customer_id: Any,
    token: str,
    request_payload: Mapping[str, Any],
    vendor_id: Optional[int] = None,
    updated_fields: Optional[Sequence[str]] = None,
) -> None:
    """Record FCM token storage during Android TV device registration."""
    message = (
        f"[fcm_register] action={action} vendor_id={vendor_id if vendor_id is not None else ''} "
        f"customer_id={customer_id} mac_address={mac_address} token={token or '(none)'} "
        f"updated_fields={','.join(updated_fields) if updated_fields else ''} "
        f"request_payload={_payload_str(request_payload)}"
    )
    for lg in _ensure_audit_loggers():
        lg.info(message)
    _flush()


def probe_fcm_audit_log() -> Path | None:
    """Write a one-line probe on startup; returns the fcm.log path if writable."""
    path = _resolve_fcm_log_path()
    if not path:
        return None
    message = f"[fcm_probe] FCM audit logging ready path={path}"
    for lg in _ensure_audit_loggers():
        lg.info(message)
    _flush()
    return path
