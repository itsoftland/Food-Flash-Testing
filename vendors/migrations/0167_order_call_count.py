from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0166_chatmessage_booking_unread_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="call_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
