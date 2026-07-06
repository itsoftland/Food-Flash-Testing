from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0167_order_call_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="mr_number_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="vendorconfig",
            name="bill_number_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
