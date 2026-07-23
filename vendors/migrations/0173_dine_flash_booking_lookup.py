# Generated manually — Dine Flash booking recovery pointer (independent of Buffet).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0172_buffet_order_lookup"),
    ]

    operations = [
        migrations.CreateModel(
            name="DineFlashBookingLookup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "order_lookup_id",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dine_flash_booking_lookup",
                        to="vendors.order",
                    ),
                ),
            ],
        ),
    ]
