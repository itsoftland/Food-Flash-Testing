from django.db import models


class DineFlashQrSession(models.Model):
    """
    Opaque tokens from dine_flash_qr_exchange, validated on home/table_booking/book_table.

    Stored in the database (not LocMemCache) so every app process shares the same rows;
    otherwise multi-worker deployments break concurrent customers (session written on one
    worker, validated on another → false "QR expired").
    """

    token = models.CharField(max_length=64, unique=True, db_index=True)
    vendor_id = models.IntegerField()
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
