# Generated manually for Dine Flash TV FCM registration storage.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0155_vendorconfig_qr_expiry_minutes"),
    ]

    operations = [
        migrations.AddField(
            model_name="androiddevice",
            name="fcm_token",
            field=models.TextField(blank=True, null=True),
        ),
    ]
