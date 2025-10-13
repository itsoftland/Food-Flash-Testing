from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order, OrderStatusHistory
from .tasks import convert_image_to_webp
from .models import AdvertisementImage
import time

from django.db import transaction
from django.dispatch import receiver
from concurrent.futures import ThreadPoolExecutor

# --- Global ThreadPool (safe reuse) ---
executor = ThreadPoolExecutor(max_workers=5)
import logging
logger = logging.getLogger(__name__)

@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    """
    Tracks any change in status, updated_by, or meaningful update to the order.
    """
    if not instance.pk:
        return  # Skip brand new orders (handled in post_save)

    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    has_status_changed = previous.status != instance.status
    has_updated_by_changed = previous.updated_by != instance.updated_by
    has_meaningful_time_change = (timezone.now() - previous.updated_at).total_seconds() > 2

    if has_status_changed or has_updated_by_changed or has_meaningful_time_change:
        OrderStatusHistory.objects.create(
            order=instance,
            previous_status=previous.status,
            new_status=instance.status,
            changed_by=instance.updated_by
        )

@receiver(post_save, sender=Order)
def create_initial_order_history(sender, instance, created, **kwargs):
    """
    Logs the initial creation of the order (first status entry).
    """
    if created:
        OrderStatusHistory.objects.create(
            order=instance,
            previous_status=None,
            new_status=instance.status,
            changed_by=instance.updated_by
        )



@receiver(post_save, sender=AdvertisementImage)
def trigger_webp_conversion(sender, instance, created, **kwargs):
    """
    Trigger WebP conversion safely after DB commit.
    Ensures background thread starts only after the object is fully saved.
    """
    if not created:
        return

    def start_conversion():
        try:
            instance.refresh_from_db()
            logger.info(f"[WebP] Queuing conversion for Image ID={instance.id}")
            executor.submit(convert_image_with_retry, instance.id)
        except Exception as e:
            logger.exception(f"[WebP] Failed to queue conversion for {instance.id}: {e}")

    # ✅ Only start after successful DB commit
    transaction.on_commit(start_conversion)

def convert_image_with_retry(ad_image_id, retries=3, delay=2):
    """
    Retry wrapper for convert_image_to_webp.
    Retries transient failures like I/O or Pillow EXIF errors.
    """
    for attempt in range(1, retries + 1):
        try:
            time.sleep(1)
            convert_image_to_webp(ad_image_id)
            logger.info(f"[WebP] Conversion successful for Image ID={ad_image_id}")
            return
        except Exception as e:
            logger.warning(f"[WebP] Attempt {attempt}/{retries} failed for {ad_image_id}: {e}")
            if attempt < retries:
                time.sleep(delay)
    logger.error(f"[WebP] All retry attempts failed for {ad_image_id}")
