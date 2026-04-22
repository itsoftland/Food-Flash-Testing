from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0154_ensure_tvdeviceconfig_utilities_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="qr_expiry_minutes",
            field=models.PositiveSmallIntegerField(default=5),
        ),
    ]
