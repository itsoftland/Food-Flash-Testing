from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order, OrderStatusHistory

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
