# vendors/utils.py
from pywebpush import webpush, WebPushException
from django.conf import settings
from .models import PushSubscription, ArchivedOrder, ArchivedOrderStatusHistory, Order, Vendor
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import transaction
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "food_flash").lower()

_DINE_FLASH_FONT_SIZE_TO_INT = {
    "small": 12,
    "medium": 16,
    "large": 20,
    "extra-large": 24,
}


_BUFFET_UTILITY_IMAGE_MAX_BYTES = 2 * 1024 * 1024
_BUFFET_UTILITY_IMAGES_MAX_COUNT = 3
_BUFFET_IMAGE_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)


def validate_buffet_utility_image_upload(upload_file):
    """
    Optional uploaded image for Dine Flash Buffet utilities.
    Returns an error message string if invalid, otherwise None.
    """
    if not upload_file:
        return None
    try:
        size = upload_file.size
    except Exception:
        return "Invalid image upload."
    if size > _BUFFET_UTILITY_IMAGE_MAX_BYTES:
        return "Image must be at most 2 MB."
    ct = (getattr(upload_file, "content_type", None) or "").lower()
    if ct and ct not in _BUFFET_IMAGE_CONTENT_TYPES:
        return "Image must be JPEG, PNG, GIF, or WebP."
    return None


def _buffet_image_record_absolute_url(request, image_record):
    if not image_record or not getattr(image_record, "image", None):
        return ""
    try:
        path = image_record.image.url
    except ValueError:
        return ""
    if request:
        return request.build_absolute_uri(path)
    return path


def _ordered_buffet_images(utility):
    return list(
        utility.buffet_images.order_by("sort_order", "id")[
            :_BUFFET_UTILITY_IMAGES_MAX_COUNT
        ]
    )


def _buffet_image_count(utility):
    count = utility.buffet_images.count()
    if count:
        return count
    field = getattr(utility, "buffet_utility_image", None)
    if field and getattr(field, "name", None):
        return 1
    return 0


def _ensure_legacy_buffet_image_migrated(utility):
    from .models import BuffetUtilityImage

    if utility.buffet_images.exists():
        return
    field = getattr(utility, "buffet_utility_image", None)
    if field and getattr(field, "name", None):
        BuffetUtilityImage.objects.create(
            utility=utility,
            image=field,
            sort_order=0,
        )


def _legacy_buffet_image_absolute_url(request, utility):
    field = getattr(utility, "buffet_utility_image", None)
    if not field or not getattr(field, "name", None):
        return ""
    try:
        path = field.url
    except ValueError:
        return ""
    if request:
        return request.build_absolute_uri(path)
    return path


def buffet_utility_image_absolute_urls(request, utility):
    """Absolute URLs for a utility's buffet images (max 3)."""
    urls = [
        url
        for img in _ordered_buffet_images(utility)
        if (url := _buffet_image_record_absolute_url(request, img))
    ]
    if urls:
        return urls
    legacy = _legacy_buffet_image_absolute_url(request, utility)
    return [legacy] if legacy else []


def buffet_utility_image_absolute_url(request, utility):
    """First buffet image URL, or empty string (backward compatible)."""
    urls = buffet_utility_image_absolute_urls(request, utility)
    return urls[0] if urls else ""


def validate_buffet_food_type(food_type):
    """Return an error message if food_type is invalid for Dine Flash Buffet utilities."""
    from .models import Utility

    if not food_type:
        return "Food type is required"
    if food_type not in (Utility.FOOD_TYPE_VEG, Utility.FOOD_TYPE_NON_VEG):
        return "Food type must be Veg or Non Veg"
    return None


def normalize_buffet_utility_description(description):
    """
    Normalize optional utility description for Dine Flash Buffet.
    Returns (value, error_message).
    """
    if description is None:
        return None, None
    description = str(description).strip()
    if not description:
        return None, None
    if len(description) > 500:
        return None, "Description must be at most 500 characters"
    return description, None


def buffet_utility_image_payload(request, utility):
    """API payload fields for buffet utility images."""
    buffet_images = []
    for img in _ordered_buffet_images(utility):
        url = _buffet_image_record_absolute_url(request, img)
        if not url:
            continue
        buffet_images.append({"id": img.id, "url": url})
    if not buffet_images:
        legacy = _legacy_buffet_image_absolute_url(request, utility)
        if legacy:
            buffet_images.append({"id": None, "url": legacy})
    urls = [item["url"] for item in buffet_images]
    return {
        "image_url": urls[0] if urls else "",
        "image_urls": urls,
        "buffet_images": buffet_images,
    }


def _parse_remove_buffet_image_ids(request_data):
    raw = request_data.get("remove_buffet_image_ids")
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        ids = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            ids = parsed if isinstance(parsed, list) else [raw]
        except (json.JSONDecodeError, TypeError):
            ids = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        return []
    result = []
    for value in ids:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _collect_buffet_upload_files(request):
    uploads = list(request.FILES.getlist("buffet_utility_images"))
    if not uploads:
        single = request.FILES.get("buffet_utility_image")
        if single:
            uploads = [single]
    return uploads


def sync_buffet_utility_legacy_image(utility):
    """Keep legacy single ImageField in sync with the first buffet image."""
    from .models import BuffetUtilityImage

    first = (
        utility.buffet_images.order_by("sort_order", "id").first()
    )
    if first:
        utility.buffet_utility_image = first.image
        utility.save(update_fields=["buffet_utility_image"])
        return
    if utility.buffet_utility_image:
        utility.buffet_utility_image.delete(save=False)
    utility.buffet_utility_image = None
    utility.save(update_fields=["buffet_utility_image"])


def clear_buffet_utility_images(utility):
    from .models import BuffetUtilityImage

    for record in BuffetUtilityImage.objects.filter(utility=utility):
        if record.image:
            record.image.delete(save=False)
        record.delete()
    if utility.buffet_utility_image:
        utility.buffet_utility_image.delete(save=False)
    utility.buffet_utility_image = None
    utility.save(update_fields=["buffet_utility_image"])


def create_buffet_utility_images(utility, upload_files):
    """Attach up to 3 images on utility create. Returns error message or None."""
    from django.db.models import Max

    from .models import BuffetUtilityImage

    uploads = list(upload_files or [])[:_BUFFET_UTILITY_IMAGES_MAX_COUNT]
    if len(upload_files or []) > _BUFFET_UTILITY_IMAGES_MAX_COUNT:
        return f"At most {_BUFFET_UTILITY_IMAGES_MAX_COUNT} images allowed per utility."
    _ensure_legacy_buffet_image_migrated(utility)
    if _buffet_image_count(utility) + len(uploads) > _BUFFET_UTILITY_IMAGES_MAX_COUNT:
        return f"At most {_BUFFET_UTILITY_IMAGES_MAX_COUNT} images allowed per utility."
    for upload in uploads:
        upload_err = validate_buffet_utility_image_upload(upload)
        if upload_err:
            return upload_err
    max_sort = utility.buffet_images.aggregate(Max("sort_order"))["sort_order__max"]
    next_sort = 0 if max_sort is None else max_sort + 1
    for upload in uploads:
        BuffetUtilityImage.objects.create(
            utility=utility,
            image=upload,
            sort_order=next_sort,
        )
        next_sort += 1
    if uploads:
        sync_buffet_utility_legacy_image(utility)
    return None


def apply_buffet_utility_image_changes(utility, request):
    """
    Update buffet images on utility edit (remove selected, clear all, add new).
    Returns error message or None.
    """
    from django.db.models import Max

    from .models import BuffetUtilityImage

    clear_all = str(
        request.data.get("clear_buffet_images", "")
        or request.data.get("clear_buffet_image", "")
    ).lower() in ("1", "true", "yes", "on")
    uploads = _collect_buffet_upload_files(request)
    remove_ids = _parse_remove_buffet_image_ids(request.data)

    if clear_all and (uploads or remove_ids):
        return "Cannot clear all images and remove or upload in the same request."
    if clear_all:
        clear_buffet_utility_images(utility)
        return None

    _ensure_legacy_buffet_image_migrated(utility)

    if remove_ids:
        for record in BuffetUtilityImage.objects.filter(
            utility=utility, id__in=remove_ids
        ):
            if record.image:
                record.image.delete(save=False)
            record.delete()

    if uploads:
        remaining = _buffet_image_count(utility)
        if remaining + len(uploads) > _BUFFET_UTILITY_IMAGES_MAX_COUNT:
            return (
                f"At most {_BUFFET_UTILITY_IMAGES_MAX_COUNT} images allowed per utility."
            )
        for upload in uploads:
            upload_err = validate_buffet_utility_image_upload(upload)
            if upload_err:
                return upload_err
        max_sort = utility.buffet_images.aggregate(Max("sort_order"))["sort_order__max"]
        next_sort = 0 if max_sort is None else max_sort + 1
        for upload in uploads:
            BuffetUtilityImage.objects.create(
                utility=utility,
                image=upload,
                sort_order=next_sort,
            )
            next_sort += 1

    if remove_ids or uploads:
        sync_buffet_utility_legacy_image(utility)
    return None


def _map_font_size_to_int(size_value):
    """
    Convert persisted enum size to Dine Flash integer size.
    Falls back to medium size when value is missing/unknown.
    """
    raw_value = str(size_value or "").strip().lower()
    if raw_value.isdigit():
        parsed = int(raw_value)
        if 1 <= parsed <= 100:
            return parsed
    return _DINE_FLASH_FONT_SIZE_TO_INT.get(raw_value, 16)


def _append_vendor_id_to_qr_url(url, vendor_id):
    """Merge vendor_id into query string; no-op if url or vendor_id is empty."""
    if not url or not vendor_id:
        return url
    parts = urlsplit(str(url).strip())
    query_pairs = list(parse_qsl(parts.query, keep_blank_values=True))
    merged = {k: v for k, v in query_pairs}
    merged["vendor_id"] = str(vendor_id).strip()
    new_query = urlencode(list(merged.items()))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def notify_web_push(order, vendor, payload, sequence_code=None, auto_delete_stale=True):
    """
    Sends web push notifications sequentially (thread-safe).
    Detects stale (404/410) subscriptions and marks or deletes them.
    """
    logger.info(
        f"🔔 Web Push Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})"
    )
    logger.debug(f"Payload: {payload}")

    # Tag outgoing web-push payload with the current project/flavour so
    # browsers can ignore unrelated notifications.
    #
    # Some call-sites may pass a dict-like object or even a JSON string;
    # normalize so `payload.project` is consistently present.
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"data": payload}
    if isinstance(payload, dict):
        payload.setdefault("project", project_name)
    else:
        # Best-effort: if it's dict-like with setdefault, use it.
        setdefault_fn = getattr(payload, "setdefault", None)
        if callable(setdefault_fn):
            payload.setdefault("project", project_name)
        else:
            payload = {"data": payload, "project": project_name}

    # Target only subscriptions explicitly linked to THIS order row (M2M).
    # Do NOT match on token_no + vendor alone: Food and Airline share the same
    # Order model and token_no can collide for the same vendor, which would
    # notify the wrong flavour's browsers.
    subscriptions = list(
        PushSubscription.objects
        .filter(tokens=order)
        .exclude(last_push_status="stale")
        .order_by("-updated_at")
        .distinct()
    )
    sub_count = len(subscriptions)
    logger.info(
        f"📦 Found {sub_count} subscription(s) for order_id={getattr(order, 'pk', None)} "
        f"token_no={getattr(order, 'token_no', None)}"
    )
    if project_name == "dine_flash" and isinstance(payload, dict):
        logger.info(
            "[dine_flash] notify_web_push subscription lookup | order_id=%s booking_id=%s "
            "status=%s type=%s subscription_count=%s",
            getattr(order, "pk", None),
            payload.get("booking_id"),
            payload.get("status"),
            payload.get("type"),
            sub_count,
        )

    if sub_count == 0:
        msg = f"No push subscriptions found for token_no={order.token_no}, vendor_id={vendor.id}"
        if project_name == "dine_flash" and isinstance(payload, dict):
            logger.warning(
                "[dine_flash] No push subscriptions for order_id=%s booking_id=%s vendor_id=%s",
                getattr(order, "pk", None),
                payload.get("booking_id"),
                vendor.id,
            )
        else:
            logger.warning(msg)
        return [msg]

    errors = []
    push_timeout_seconds = int(getattr(settings, "WEB_PUSH_TIMEOUT_SECONDS", 5))

    def _send_one_subscription(sub):
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            ttl=60,
            timeout=push_timeout_seconds,
        )
        return sub, None

    max_workers = min(max(sub_count, 1), 6)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_send_one_subscription, sub): sub for sub in subscriptions}
        for future in as_completed(future_map):
            sub = future_map[future]
            try:
                _, _ = future.result()
                sub.mark_as_success()
                if project_name == "dine_flash":
                    logger.info(
                        "[dine_flash] Web push delivered | subscription_id=%s browser_id=%s "
                        "order_id=%s",
                        sub.id,
                        sub.browser_id,
                        getattr(order, "pk", None),
                    )
                try:
                    save_server_chat_message(payload, vendor, sub, sequence_code)
                except Exception as chat_err:
                    logger.warning(f"💬 Chat save failed: {chat_err}")
            except WebPushException as ex:
                response_status = getattr(ex.response, "status_code", None)
                response_text = getattr(ex.response, "text", str(ex))

                if response_status in (404, 410):
                    msg = (
                        f"⚠️ Stale subscription detected (status {response_status}) "
                        f"for endpoint={sub.endpoint}"
                    )
                    logger.warning(msg)
                    sub.mark_as_stale(response_text)

                    if auto_delete_stale:
                        sub.delete()
                        logger.info(f"🧹 Deleted stale subscription for {sub.browser_id}")
                else:
                    msg = (
                        f"❌ Push failed (status={response_status}) for endpoint={sub.endpoint}: {ex}"
                    )
                    logger.error(msg)
                    sub.last_push_status = 'failed'
                    sub.last_push_response = response_text
                    sub.save(update_fields=['last_push_status', 'last_push_response', 'updated_at'])

                errors.append(msg)
            except Exception as e:
                msg = f"❌ Unexpected error sending push to {sub.endpoint}: {e}"
                logger.exception(msg)
                errors.append(msg)

    logger.info(f"📬 Push complete: {sub_count - len(errors)} success, {len(errors)} failed.")
    return errors

def send_push_notification(subscription_info, payload):
    try:
        # Ensure the payload is tagged so the PWA can ignore cross-flavour messages.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"data": payload}
        if isinstance(payload, dict):
            payload.setdefault("project", project_name)
        else:
            setdefault_fn = getattr(payload, "setdefault", None)
            if callable(setdefault_fn):
                payload.setdefault("project", project_name)
            else:
                payload = {"data": payload, "project": project_name}
        logger.info("Attempting to send web push notification.")
        logger.debug("Payload: %s", json.dumps(payload, indent=2))
        logger.debug("Subscription Info: %s", json.dumps(subscription_info, indent=2))

        headers = {
            "Content-Type": "application/json"
        }

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:sanju.softland@gmail.com"},
            headers=headers
        )

        logger.info("Web push notification sent successfully.")
        return True

    except WebPushException as ex:
        logger.error("Web push failed for subscription: %s", subscription_info)
        logger.exception("Exception during web push: %s", repr(ex))
        return False

    except Exception as e:
        logger.exception("Unexpected error in web push notification: %s", str(e))
        return False

import uuid
from django.utils.timezone import now
from vendors.models import WebChatMessage


def save_server_chat_message(payload, vendor,subscription,sequence_code=None):
    """
    Save a server-side chat message (order updates, manager messages, etc.)
    into the WebChatMessage table.

    Args:
        payload (dict): Expected to contain fields like:
                        token_no, sender, type, text/title/body/status.
        vendor (Vendor): Vendor instance.

    Returns:
        WebChatMessage instance
    """
    try:
        token_no = payload.get("token_no")
        msg_type = payload.get("type")
        booking_id = payload.get("booking_id")

        # Build text as JSON (ensures consistent format)
        text = payload
        # 🧩 Airline Flash special handling: get token_no from sequence_code
        if project_name == "airline_flash" and sequence_code:    
            message = WebChatMessage.objects.create(
                message_id=uuid.uuid4(),
                subscription=subscription,
                vendor=vendor,
                token_no=token_no,
                sequence_code=sequence_code,
                sender="server",
                type=msg_type,
                text=text,
                timestamp=now(),
                is_read=False,
                is_send=True
            )
        elif project_name in ["dine_flash", "dine_flash_buffet"] and booking_id:
            message = WebChatMessage.objects.create(
                message_id=uuid.uuid4(),
                subscription=subscription,
                vendor=vendor,
                token_no=token_no,
                booking_id=booking_id,
                sender="server",
                type=msg_type,
                text=text,
                timestamp=now(),
                is_read=False,
                is_send=True
            )
            if project_name == "dine_flash":
                logger.info(
                    "[dine_flash] save_server_chat_message | message_id=%s booking_id=%s "
                    "subscription_id=%s browser_id=%s type=%s status=%s",
                    message.message_id,
                    booking_id,
                    subscription.id,
                    subscription.browser_id,
                    msg_type,
                    payload.get("status"),
                )
        else:
            message = WebChatMessage.objects.create(
                message_id=uuid.uuid4(),
                subscription=subscription,
                vendor=vendor,
                token_no=token_no,
                sender="server",
                type=msg_type,
                text=text,
                timestamp=now(),
                is_read=False,
                is_send=True
            )

        return message

    except Exception as e:
        # Don’t raise — just log and move on, since chat should not block order update
        logger.error("[save_server_chat_message] Failed: %s", e)
        return None


def archive_order(order):
    try:
        with transaction.atomic():
            # Step 1: Create archived order
            archived_order = ArchivedOrder.objects.create(
                original_order_id=order.id,
                vendor=order.vendor,
                device=order.device,
                user_profile=order.user_profile,
                token_no=order.token_no,
                status=order.status,
                counter_no=order.counter_no,
                shown_on_tv=order.shown_on_tv,
                notified_at=order.notified_at,
                updated_by=order.updated_by,
                created_at=order.created_at,
                updated_at=order.updated_at,
                created_date=order.created_date
            )

            # Step 2: Copy status history
            histories = order.status_history.all()
            if histories.exists():
                bulk_data = [
                    ArchivedOrderStatusHistory(
                        archived_order=archived_order,
                        previous_status=h.previous_status,
                        new_status=h.new_status,
                        changed_by=h.changed_by,
                        changed_at=h.changed_at
                    )
                    for h in histories
                ]
                ArchivedOrderStatusHistory.objects.bulk_create(bulk_data)
                logger.info(f"Archived {len(bulk_data)} status history records for Order {order.token_no}")

            else:
                logger.info(f"No status history found for Order {order.token_no}")

            logger.info(f"Successfully archived Order {order.token_no} (Vendor ID {order.vendor_id})")

    except Exception as e:
        logger.error(f"Error archiving order {order.id} (token {order.token_no}): {e}")

def build_tv_config_payload(
    tv_config,
    request=None,
    omit_utilities=False,
    include_dine_flash_fields=False,
    vendor_id=None,
):
    """
    Builds a standardized payload for TVDeviceConfig,
    dynamically resolving utility label based on utility_name_mode.
    Includes Dine Flash specific fields if applicable.

    When omit_utilities is True (Dine Flash TV registration), the payload omits the
    ``utilities`` key so the client does not receive utility lists or labels.
    """
    if not tv_config:
        return None

    is_dine_flash = bool(include_dine_flash_fields)

    utilities_data = []
    if not omit_utilities:
        mode = tv_config.utility_name_mode  # utility_name / display_name / display_code
        for u in tv_config.utilities.filter(is_active=True):
            label_value = getattr(u, mode, None)  # dynamically pick field
            utilities_data.append({
                "id": u.id,
                "label": label_value,
            })

    # Base payload compatible with all variants
    payload = {
        "show_qr": tv_config.show_qr,
        "items_to_show": tv_config.items_to_show,
        "booking_fields": tv_config.booking_fields,
        "utility_name_mode": tv_config.utility_name_mode,
        "screen_orientation": tv_config.screen_orientation,
        "created_at": tv_config.created_at,
        "updated_at": tv_config.updated_at,
    }
    if not omit_utilities:
        payload["utilities"] = utilities_data

    # Keep qr_alignment in the response contract for all variants, including Dine Flash.
    payload["qr_alignment"] = tv_config.qr_alignment if tv_config.show_qr else None

    # Dine Flash Specific Scope
    if is_dine_flash:
        payload.pop("booking_fields", None)
        # Add Extended Display settings
        payload.update({
            "display_rows": tv_config.display_rows,
            "display_columns": tv_config.display_columns,
            "token_font_size": _map_font_size_to_int(tv_config.token_font_size),
            "counter_font_size": _map_font_size_to_int(tv_config.counter_font_size),
            "utility_font_size": _map_font_size_to_int(tv_config.utility_font_size),
            "token_text_color": tv_config.token_text_color,
            "counter_text_color": tv_config.counter_text_color,
            "utility_text_color": tv_config.utility_text_color,
            "show_customer_name": tv_config.show_customer_name,
            "show_phone_number": tv_config.show_phone_number,
            "show_partially_masked_phone_number": getattr(tv_config, "show_partially_masked_phone_number", False),
            # Keep explicit toggle name expected by Android TV clients.
            "show_no_of_packs": tv_config.show_order_details,
            "audio_enabled": tv_config.audio_enabled,
            "announcement_language": tv_config.announcement_language,
            "blink_token": tv_config.blink_token,
            "blink_utility": tv_config.blink_utility,
            "enable_ads": tv_config.enable_ads,
            "header_font_size": _map_font_size_to_int(getattr(tv_config, "header_font_size", "large")),
            "header_font_style": getattr(tv_config, "header_font_style", "bold"),
            "header_text_color": getattr(tv_config, "header_text_color", "#000000"),
            "footer_font_size": _map_font_size_to_int(getattr(tv_config, "footer_font_size", "16")),
            "footer_text_color": getattr(tv_config, "footer_text_color", "#000000"),
            "footer_enabled": getattr(tv_config, "footer_enabled", False),
            "footer_texts": (tv_config.footer_texts or []) if getattr(tv_config, "footer_enabled", False) else [],
        })

        # QR Code Extended Logic
        if tv_config.show_qr:
            qr_url = tv_config.qr_base_url
            if not qr_url and request:
                # Default to dynamic project path if empty
                qr_url = request.build_absolute_uri('/dine_flash/table_booking/')
            if qr_url:
                # Android TV appends hashed QR params client-side; omit vendor_id here.
                parts = urlsplit(str(qr_url).strip())
                qr_url = (
                    urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/'), '', ''))
                    + '/?'
                )

            payload.update({
                "qr_placement": tv_config.qr_placement,
                "qr_base_url": qr_url,
                "qr_expiry_minutes": getattr(tv_config, "qr_expiry_minutes", 5),
            })
        else:
            # Explicitly exclude or nullify if QR is disabled for Dine Flash
            payload["qr_placement"] = None
            payload["qr_base_url"] = None
            payload["qr_expiry_minutes"] = None

        if tv_config.enable_ads:
            payload.update({
                "ad_position": tv_config.ad_position,
                "ad_interval": tv_config.ad_interval,
                "video_ad_mode": getattr(tv_config, "video_ad_mode", "play_full"),
            })
            ad_urls = []
            ad_queryset = tv_config.advertisements.filter(is_active=True).order_by("sequence", "created_at", "id")
            for ad in ad_queryset:
                if not ad.media_file:
                    continue
                media_url = request.build_absolute_uri(ad.media_file.url) if request else ad.media_file.url
                ad_urls.append(media_url)

            # Contract for Android TV: each advertisement URL as a separate string.
            # - multiple ads -> ["url1", "url2", ...]
            # - single ad    -> ["url1"]
            # - no ads       -> []
            payload["ad_items"] = ad_urls

    return payload


# Dine Flash: queue / table statuses (see core.config.status_choices.STATUS_CHOICES_MAP)
_DINE_FLASH_WAITING_STATUSES = frozenset({"created", "waiting"})
# "occupied" should remain visible on TV as an ongoing table state.
_DINE_FLASH_ACTIVE_TABLE_STATUSES = frozenset({"allocated", "occupied"})
_DINE_FLASH_EXCLUDED_STATUSES = frozenset({"booking_cancelled", "operation_closed"})
_DINE_FLASH_QR_DATE_FORMAT = "%Y-%m-%d"
_DINE_FLASH_QR_TIME_FORMAT = "%H:%M:%S"
_DINE_FLASH_QR_TIME_FORMAT_LABEL = "24_hour"
_DINE_FLASH_QR_DATE_PART_DIGITS = {"year": 4, "month": 2, "day": 2}
_DINE_FLASH_QR_TIME_PART_DIGITS = {"hour": 2, "minute": 2, "second": 2}


def build_dine_flash_tv_booking_snapshot(vendor, tv_config, request=None):
    """
    Initial TV payload for Dine Flash: waiting queue + seated/active tables for the
    current business day for the vendor. Respects TV visibility settings
    (booking_fields, items_to_show) but does not filter by utility.
    """
    from django.urls import reverse
    from django.utils import timezone as django_timezone
    from static.utils.functions.utils import get_vendor_business_day_range, get_vendor_current_date

    # Resolve the same Vendor row book_table uses: unique business vendor_id (AndroidDevice FK can be stale).
    if vendor is not None:
        canonical = (
            Vendor.objects.select_related("config")
            .filter(vendor_id=vendor.vendor_id)
            .first()
        )
        if canonical is not None:
            vendor = canonical

    def build_empty_snapshot():
        return {
            "display_mode": "table_booking",
            # Frontend contract:
            # - tv_config => display behavior/config controls
            # - dine_flash => booking/table data payload
            "data_source": "dine_flash",
            "vendor_id": vendor.vendor_id,
            "location_id": getattr(vendor, "location_id", None),
            "waiting": [],
            # Keep active_tables for backward compatibility, add clearer alias.
            "active_tables": [],
            "ongoing_tables": [],
            "counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
            "displayed_counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
            "table_booking_url": None,
            # Dine Flash QR workflow: Android TV receives this base tracking URL
            # and appends dynamic date/time params while generating the QR payload.
            "tracking_qr_base_url": None,
            "qr_expiry_minutes": None,
            "qr_date_format": _DINE_FLASH_QR_DATE_FORMAT,
            "qr_time_format": _DINE_FLASH_QR_TIME_FORMAT,
            "qr_time_format_label": _DINE_FLASH_QR_TIME_FORMAT_LABEL,
            "qr_date_part_digits": _DINE_FLASH_QR_DATE_PART_DIGITS,
            "qr_time_part_digits": _DINE_FLASH_QR_TIME_PART_DIGITS,
        }

    start_dt, end_dt = get_vendor_business_day_range(vendor)
    if not start_dt or not end_dt:
        return build_empty_snapshot()

    # Resolve "today" safely (Vendor.config is required elsewhere for Dine Flash, but be defensive).
    try:
        vendor_today = get_vendor_current_date(vendor)
    except Exception as exc:
        logger.warning(
            "build_dine_flash_tv_booking_snapshot: get_vendor_current_date failed vendor_id=%s: %s",
            getattr(vendor, "vendor_id", None),
            exc,
        )
        vendor_today = django_timezone.now().date()

    utc_today = django_timezone.now().date()
    # Calendar backup for primary window only: outlet-local "today" and UTC "today" on Order.created_date.
    # (Avoid ±1 day here — that pulled stale rows into the main path; business-day coverage is in_window.)
    date_keys = {vendor_today, utc_today}

    # Avoid Q(...) | Q(...) + distinct(): some MySQL configs mis-handle OR+distinct; merge IDs instead.
    vid = vendor.id
    in_window = Order.objects.filter(
        vendor_id=vid,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    ).values_list("id", flat=True)
    by_calendar = Order.objects.filter(
        vendor_id=vid,
        created_date__in=date_keys,
    ).values_list("id", flat=True)
    order_ids = set(in_window) | set(by_calendar)
    qs = Order.objects.filter(id__in=order_ids).exclude(status__in=_DINE_FLASH_EXCLUDED_STATUSES)

    booking_fields = (
        list(tv_config.booking_fields)
        if tv_config and tv_config.booking_fields
        else ["name", "phone", "guest_count", "datetime", "token"]
    )
    max_items = int(getattr(tv_config, "items_to_show", 5) or 5) if tv_config else 5
    max_items = max(1, min(max_items, 5))

    def _mask_phone_number(phone):
        raw = str(phone or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) < 4:
            return raw
        visible_tail = digits[-4:]
        masked_prefix = "*" * max(len(digits) - 4, 0)
        return f"{masked_prefix}{visible_tail}"

    show_customer_name = getattr(tv_config, "show_customer_name", True) if tv_config else True
    show_phone = getattr(tv_config, "show_phone_number", True) if tv_config else True
    show_partial_phone = getattr(tv_config, "show_partially_masked_phone_number", False) if tv_config else False
    show_order_details = getattr(tv_config, "show_order_details", True) if tv_config else True
    show_no_of_packs = getattr(tv_config, "show_order_details", True) if tv_config else True

    def _seat_display(order):
        raw = getattr(order, "seat_no", None)
        if raw is None:
            return ""
        s = raw.strip() if isinstance(raw, str) else str(raw).strip()
        return s

    def serialize_row(order):
        row = {
            "id": order.id,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        seat_display = _seat_display(order)
        if seat_display:
            row["seat_no"] = seat_display

        # Dine Flash TV: always send booking id + table/seat line (do not gate on booking_fields).
        # TV configs often omit legacy "token" in booking_fields; without this, table_booking_no /
        # seat never appear. Optional columns (name, phone, …) still follow booking_fields below.
        booking_no = (order.table_booking_no or "").strip() if order.table_booking_no else ""
        row["table_booking_no"] = order.table_booking_no
        row["token_no"] = order.token_no
        if booking_no and seat_display:
            row["table_booking_no_display"] = f"{booking_no} [{seat_display}]"
        elif booking_no:
            row["table_booking_no_display"] = booking_no
        elif seat_display:
            row["table_booking_no_display"] = f"[{seat_display}]"

        if "name" in booking_fields and show_customer_name:
            row["customer_name"] = order.customer_name
        if "phone" in booking_fields and show_phone:
            row["phone_number"] = _mask_phone_number(order.phone_number) if show_partial_phone else order.phone_number
        if show_no_of_packs:
            row["guest_count"] = order.no_of_packs
            row["no_of_packs"] = order.no_of_packs
            row["packs"] = order.no_of_packs
        if "datetime" in booking_fields:
            row["booked_at"] = order.created_at.isoformat() if order.created_at else None
        if show_order_details and order.remarks:
            row["remarks"] = order.remarks
        return row

    waiting_qs = qs.filter(status__in=_DINE_FLASH_WAITING_STATUSES).order_by("created_at")
    active_qs = qs.filter(status__in=_DINE_FLASH_ACTIVE_TABLE_STATUSES).order_by("-created_at")

    waiting = [serialize_row(o) for o in waiting_qs[:max_items]]
    active_tables = [serialize_row(o) for o in active_qs[:max_items]]

    table_booking_url = None
    tracking_qr_base_url = None
    if request:
        try:
            path = reverse("table_booking")
            table_booking_url = request.build_absolute_uri(f"{path}?vendor_id={vendor.vendor_id}")
        except Exception:
            if getattr(settings, "PROJECT_NAME", ""):
                table_booking_url = request.build_absolute_uri(
                    f"/{settings.PROJECT_NAME}/table_booking/?vendor_id={vendor.vendor_id}"
                )
        # Dynamic QR base should open the booking form first (not home).
        tracking_qr_base_url = table_booking_url

    payload = {
        "display_mode": "table_booking",
        "data_source": "dine_flash",
        "vendor_id": vendor.vendor_id,
        "location_id": getattr(vendor, "location_id", None),
        "waiting": waiting,
        "active_tables": active_tables,
        "ongoing_tables": active_tables,  # clearer alias for frontend readability
        "counts": {
            "waiting": waiting_qs.count(),
            "active_tables": active_qs.count(),
            "ongoing_tables": active_qs.count(),
        },
        # Display-limited counts for UI rendering indicators
        "displayed_counts": {
            "waiting": len(waiting),
            "active_tables": len(active_tables),
            "ongoing_tables": len(active_tables),
        },
        "table_booking_url": table_booking_url,
        "tracking_qr_base_url": tracking_qr_base_url,
        "qr_expiry_minutes": getattr(tv_config, "qr_expiry_minutes", None) if tv_config else None,
        "qr_date_format": _DINE_FLASH_QR_DATE_FORMAT,
        "qr_time_format": _DINE_FLASH_QR_TIME_FORMAT,
        "qr_time_format_label": _DINE_FLASH_QR_TIME_FORMAT_LABEL,
        "qr_date_part_digits": _DINE_FLASH_QR_DATE_PART_DIGITS,
        "qr_time_part_digits": _DINE_FLASH_QR_TIME_PART_DIGITS,
    }
    return payload


def build_vendor_config_payload(vendor):
    """
    Builds a minimal vendor configuration payload for Android APK.
    Returns safe defaults if config is missing.
    """
    try:
        config = vendor.config
        return {
            "phone_number_enabled": config.phone_number_enabled,
            "utilities_enabled": config.use_utilities,
        }
    except Exception:
        return {
            "phone_number_enabled": False,
            "utilities_enabled": False,
        }



