# vendors/utils.py
from pywebpush import webpush, WebPushException
from django.conf import settings
from .models import PushSubscription, ArchivedOrder
import json
import logging

logger = logging.getLogger(__name__)

def notify_web_push(order, vendor, payload):
    logger.info(f"🔔 Web Push Notification Initiated | Token: {order.token_no}, Vendor: {vendor.name} (ID: {vendor.id})")
    logger.debug(f"Payload: {payload}")

    subscriptions = PushSubscription.objects.filter(tokens__token_no=order.token_no, tokens__vendor=vendor).distinct()
    subscription_count = subscriptions.count()
    logger.info(f"📦 Found {subscription_count} subscription(s) for token_no={order.token_no} and vendor_id={vendor.id}")

    errors = []

    # 🔹 If no subscriptions found, return early with reason
    if subscription_count == 0:
        msg = f"No push subscriptions found for token_no={order.token_no} and vendor_id={vendor.id}"
        logger.warning(f"⚠️ {msg}")
        return [msg]  # ✅ Return None instead of a message inside a list

    for sub in subscriptions:
        logger.debug(f"Sending push to endpoint: {sub.endpoint}")
        success = send_push_notification({
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
        }, payload)

        if not success:
            error_msg = f"❌ Push failed for endpoint {sub.endpoint}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(f"📬 Notification completed with {len(errors)} error(s).")
    return errors


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

def archive_order(order):
    ArchivedOrder.objects.create(
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
