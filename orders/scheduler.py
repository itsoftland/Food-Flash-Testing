import logging
from datetime import timedelta
from django.db import connection, models
from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from vendors.models import Order, PushSubscription
from vendors.utils import archive_order

# Setup logger
logger = logging.getLogger(__name__)

def auto_clear_orders():
    try:
        connection.ensure_connection()
        if not connection.is_usable():
            logger.warning("Database connection is not usable.")
            return
        logger.info("Database connection is active.")

        now = timezone.now()

        from vendors.models import AdminOutlet, Vendor, VendorConfig  # local import to avoid circularity

        admin_outlets = AdminOutlet.objects.all()

        for admin_outlet in admin_outlets:
            vendors = admin_outlet.vendors.select_related("config").all()

            for vendor in vendors:
                config = getattr(vendor, "config", None)

                # 1️⃣ If no VendorConfig found → skip vendor
                if not config:
                    logger.warning(f"Skipping vendor '{vendor.name}' (ID {vendor.id}) — no VendorConfig found.")
                    continue

                delete_hours = config.auto_delete_hours

                # 2️⃣ If deletion disabled → skip vendor
                if delete_hours is None:
                    logger.info(f"Skipping vendor '{vendor.name}' — auto-deletion disabled in config.")
                    continue

                # 3️⃣ Ensure minimum 2 hours
                if delete_hours < 2:
                    logger.warning(f"Vendor '{vendor.name}' has invalid auto_delete_hours ({delete_hours}), using 2h fallback.")
                    delete_hours = 2

                delete_threshold = now - timedelta(hours=delete_hours)

                # 4️⃣ Select orders for deletion
                orders_to_delete = Order.objects.filter(
                    vendor=vendor
                ).filter(
                    models.Q(updated_at__lt=delete_threshold) |
                    models.Q(created_at__lt=delete_threshold)
                )

                count = orders_to_delete.count()
                if count > 0:
                    logger.info(
                        f"Deleting {count} orders for Vendor '{vendor.name}' "
                        f"(Outlet: {admin_outlet.customer_name}, Vendor ID: {vendor.id})"
                    )

                    for order in orders_to_delete:
                        logger.info(f"Archiving and deleting Order {order.token_no} (Vendor ID {vendor.id})")

                        # Archive logic (if implemented)
                        archive_order(order)

                        # Remove from all subscriptions
                        for sub in order.pushsubscription_set.all():
                            sub.tokens.remove(order)

                        order.delete()

        # 5️⃣ Remove orphaned PushSubscriptions
        orphaned_subs = PushSubscription.objects.annotate(
            token_count=models.Count('tokens')
        ).filter(token_count=0)

        orphaned_count = orphaned_subs.count()
        if orphaned_count:
            logger.info(f"Deleting {orphaned_count} orphaned PushSubscriptions...")
            orphaned_subs.delete()

    except Exception as e:
        logger.error(f"Error during auto_clear_orders: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_clear_orders, 'interval', minutes=5)  # Run every 5 minutes
    scheduler.start()
    logger.info("Scheduler started, running auto_clear_orders every 5 minutes.")

