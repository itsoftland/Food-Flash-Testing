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


# ============================================================
# PRE-SAVE SIGNAL → TRACK STATUS / UPDATED_BY / UTILITY CHANGES
# ============================================================
@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    """
    Tracks changes to an existing Order before it is saved.

    This signal compares the in-memory `instance` with the stored `previous`
    version from the database. If any of the following fields change, it creates
    a new OrderStatusHistory entry BEFORE the actual save:

    1. status          → workflow change
    2. updated_by      → who performed the update
    3. utility_id      → customer moved from one utility to another
    4. meaningful time change (>2 seconds since last update)

    Notes:
    - Runs only for updates (not new orders).
    - Purpose is to create a clean audit trail of transitions.
    """

    # Case: New order → history handled in post_save
    if not instance.pk:
        return

    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    # Detect changes
    has_status_changed = previous.status != instance.status
    has_updated_by_changed = previous.updated_by != instance.updated_by
    has_utility_changed = previous.utility_id != instance.utility_id
    has_meaningful_time_change = (
        timezone.now() - previous.updated_at
    ).total_seconds() > 2

    if not (
        has_status_changed
        or has_updated_by_changed
        or has_utility_changed
        or has_meaningful_time_change
    ):
        return  # no significant change → skip history creation

    # ============================================================
    # PROCESSING TIME CALCULATION
    # ============================================================
    previous_history = (
        OrderStatusHistory.objects
        .filter(order=instance)
        .order_by('-changed_at')
        .first()
    )

    processing_time_seconds = None
    now = timezone.now()

    if previous_history:
        last_time = previous_history.changed_at
        processing_time_seconds = int((now - last_time).total_seconds())

    # ============================================================
    # CREATE HISTORY ENTRY
    # ============================================================
    OrderStatusHistory.objects.create(
        order=instance,
        previous_status=previous.status,
        new_status=instance.status,
        previous_utility=previous.utility,
        new_utility=instance.utility,
        changed_by=instance.updated_by,
        processing_time_seconds=processing_time_seconds,  # ← STORED HERE
    )

    logger.info(
        f"[HISTORY] Order {instance.id}: "
        f"{previous.status} → {instance.status}, "
        f"Utility {previous.utility_id} → {instance.utility_id}, "
        f"Time Spent: {processing_time_seconds}s"
    )

# ============================================================
# POST-SAVE SIGNAL → CREATION HISTORY ENTRY
# ============================================================
@receiver(post_save, sender=Order)
def create_initial_order_history(sender, instance, created, **kwargs):
    """
    Creates the initial OrderStatusHistory entry when a new Order is created.

    This signal runs immediately after an Order has been saved to the database.
    If 'created' is True, it indicates that this is the first save (new booking).

    In this case, a history record is created to log the initial status of the Order.
    This ensures that the very first state of the order is included in the
    timeline of historical events.

    Purpose:
    --------
    Ensures that every Order has at least one history entry from the moment of
    creation, maintaining a complete lifecycle history.
    """
    if created:
        OrderStatusHistory.objects.create(
            order=instance,
            previous_status=None,
            new_status=instance.status,
            previous_utility=None,
            new_utility=instance.utility,
            changed_by=instance.updated_by,
            processing_time_seconds=0,  # first entry always zero
        )

        logger.info(
            f"[HISTORY - INIT] Order {instance.id}: Created with status "
            f"'{instance.status}' and utility '{instance.utility_id}'"
        )
# ============================================================
# POST-SAVE SIGNAL → ASYNC WEBP CONVERSION
# ============================================================

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

# ============================================================
# WEBP CONVERSION WITH RETRIES
# ============================================================
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
