# Generated manually for Buffet Active Order Registry (Phase 1).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0173_dine_flash_booking_lookup"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuffetActiveOrder",
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
                ("token_no", models.IntegerField()),
                ("vendor_id", models.IntegerField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buffet_active_order",
                        to="vendors.order",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="buffetactiveorder",
            index=models.Index(
                fields=["order_lookup_id", "vendor_id"],
                name="buffet_act_vendor_idx",
            ),
        ),
    ]
