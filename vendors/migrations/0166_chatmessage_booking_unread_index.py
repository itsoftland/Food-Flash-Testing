from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0165_utility_description"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="chatmessage",
            index=models.Index(
                fields=["vendor", "booking_id", "sender", "is_read"],
                name="chatmsg_vendor_booking_unread",
            ),
        ),
    ]
