# Generated manually for Dine Flash Active Booking Registry.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0181_buffetsavedtableqr"),
    ]

    operations = [
        migrations.CreateModel(
            name="DineFlashActiveBooking",
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
                ("order_lookup_id", models.CharField(db_index=True, max_length=255)),
                ("table_booking_no", models.CharField(max_length=64)),
                ("vendor_id", models.IntegerField(db_index=True)),
                ("token_no", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dine_flash_active_booking",
                        to="vendors.order",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="dineflashactivebooking",
            index=models.Index(
                fields=["order_lookup_id", "vendor_id"],
                name="dine_flash_act_vendor_idx",
            ),
        ),
    ]
