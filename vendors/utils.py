# vendors/utils.py
from pywebpush import webpush, WebPushException
from django.conf import settings
from .models import PushSubscription, ArchivedOrder,ArchivedOrderStatusHistory
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import transaction
import json
import logging

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "food_flash").lower()

def notify_web_push(order, vendor, payload, sequence_code=None, auto_delete_stale=True):
    """
    Sends web push notifications sequentially (thread-safe).
    Detects stale (404/410) subscriptions and marks or deletes them.
    """
    logger.info(
        f"🔔 Web Push Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})"
    )
    logger.debug(f"Payload: {payload}")

    subscriptions = list(
        PushSubscription.objects.filter(
            tokens__token_no=order.token_no,
            tokens__vendor=vendor
        ).distinct()
    )
    sub_count = len(subscriptions)
    logger.info(f"📦 Found {sub_count} subscription(s) for token_no={order.token_no}")

    if sub_count == 0:
        msg = f"No push subscriptions found for token_no={order.token_no}, vendor_id={vendor.id}"
        logger.warning(msg)
        return [msg]

    errors = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
                ttl=60,
            )

            # ✅ Mark as success
            sub.mark_as_success()

            # Save chat copy if applicable
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

#integrated sendpush also inside this
# def notify_web_push(order, vendor, payload, sequence_code=None):
#     """
#     Sends web push notifications sequentially (no internal ThreadPool).
#     Concurrency is now handled by outer layer (manager_order_update).
#     Returns an empty list on full success, or a list of error messages on failure.
#     """
#     logger.info(
#         f"🔔 Web Push Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})"
#     )
#     logger.debug(f"Payload: {payload}")

#     subscriptions = list(
#         PushSubscription.objects.filter(
#             tokens__token_no=order.token_no,
#             tokens__vendor=vendor
#         ).distinct()
#     )
#     sub_count = len(subscriptions)
#     logger.info(f"📦 Found {sub_count} subscription(s) for token_no={order.token_no}")

#     if sub_count == 0:
#         msg = f"No push subscriptions found for token_no={order.token_no}, vendor_id={vendor.id}"
#         logger.warning(msg)
#         return [msg]

#     errors = []

#     for sub in subscriptions:
#         try:
#             # ---- Send push ----
#             webpush(
#                 subscription_info={
#                     "endpoint": sub.endpoint,
#                     "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
#                 },
#                 data=json.dumps(payload),
#                 vapid_private_key=settings.VAPID_PRIVATE_KEY,
#                 vapid_claims={
#                     "sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}",
#                 },
#                 ttl=60,
#             )
#             # ---- Save chat copy if required ----
#             try:
#                 save_server_chat_message(payload, vendor, sub, sequence_code)
#             except Exception as chat_err:
#                 logger.warning(f"💬 Chat save failed: {chat_err}")

#         except WebPushException as ex:
#             msg = f"❌ Push failed for endpoint={sub.endpoint}: {str(ex)}"
#             logger.error(msg)
#             errors.append(msg)
#         except Exception as e:
#             msg = f"❌ Unexpected error sending push: {e}"
#             logger.exception(msg)
#             errors.append(msg)

#     logger.info(f"📬 Push complete: {sub_count - len(errors)} success, {len(errors)} failed.")
#     return errors
#old one
# def notify_web_push(order, vendor, payload, sequence_code=None):
#     logger.info(
#         f"🔔 Web Push Notification Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})"
#     )
#     logger.debug(f"Payload: {payload}")

#     subscriptions = list(
#         PushSubscription.objects.filter(
#             tokens__token_no=order.token_no,
#             tokens__vendor=vendor
#         ).distinct()
#     )
#     subscription_count = len(subscriptions)
#     logger.info(
#         f"📦 Found {subscription_count} subscription(s) for token_no={order.token_no} and vendor_id={vendor.id}"
#     )

#     if subscription_count == 0:
#         msg = f"No push subscriptions found for token_no={order.token_no} and vendor_id={vendor.id}"
#         logger.warning(f"⚠️ {msg}")
#         return [msg]

#     errors = []

#     # --- 🔹 Parallel push sending ---
#     def push_one(sub):
#         success = send_push_notification(
#             {"endpoint": sub.endpoint,
#              "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
#             payload
#         )
#         save_server_chat_message(payload, vendor, sub, sequence_code)
#         return (sub.endpoint, success)

#     # Run up to 20 concurrent sends; adjust if server has more capacity
#     with ThreadPoolExecutor(max_workers=20) as executor:
#         futures = [executor.submit(push_one, s) for s in subscriptions]

#         for future in as_completed(futures):
#             endpoint, success = future.result()
#             if not success:
#                 error_msg = f"❌ Push failed for endpoint {endpoint}"
#                 logger.error(error_msg)
#                 errors.append(error_msg)

#     logger.info(f"📬 Notification completed with {len(errors)} error(s).")
#     return errors

# def notify_web_push(order, vendor, payload,sequence_code=None):
#     logger.info(f"🔔 Web Push Notification Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})")
#     logger.debug(f"Payload: {payload}")

#     subscriptions = PushSubscription.objects.filter(tokens__token_no=order.token_no, tokens__vendor=vendor).distinct()
#     subscription_count = subscriptions.count()
#     logger.info(f"📦 Found {subscription_count} subscription(s) for token_no={order.token_no} and vendor_id={vendor.id}")

#     errors = []

#     # 🔹 If no subscriptions found, return early with reason
#     if subscription_count == 0:
#         msg = f"No push subscriptions found for token_no={order.token_no} and vendor_id={vendor.id}"
#         logger.warning(f"⚠️ {msg}")
#         return [msg]  # ✅ Return None instead of a message inside a list

#     for sub in subscriptions:
#         logger.debug(f"Sending push to endpoint: {sub.endpoint}")
#         success = send_push_notification({
#             "endpoint": sub.endpoint,
#             "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
#         }, payload)
#         save_server_chat_message(payload, vendor, sub,sequence_code)
#         if not success:
#             error_msg = f"❌ Push failed for endpoint {sub.endpoint}"
#             logger.error(error_msg)
#             errors.append(error_msg)

#     logger.info(f"📬 Notification completed with {len(errors)} error(s).")
#     return errors


def send_push_notification(subscription_info, payload):
    try:
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
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[save_server_chat_message] Failed: {e}")
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
