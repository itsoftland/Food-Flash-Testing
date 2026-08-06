# Generated manually for Hospital Flash announcement templates

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0175_order_pre_announcement_notified_distance"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="announcement_templates",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Hospital Flash: spoken announcement template selections (unused by other flavours)",
            ),
        ),
    ]
