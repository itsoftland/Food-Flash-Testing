from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0151_tvdeviceconfig_header_footer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="qr_expiry_minutes",
            field=models.PositiveSmallIntegerField(default=5),
        ),
    ]

