from django.db import migrations, models
import uuid

class Migration(migrations.Migration):

    dependencies = [
        ('vendors', '0098_advertisementimage_is_converted'),  # replace with your latest migration
    ]

    operations = [
        # Update ChatMessage.message_id
        migrations.AlterField(
            model_name='chatmessage',
            name='message_id',
            field=models.CharField(
                max_length=36,
                default=uuid.uuid4,
                unique=True,
                editable=False
            ),
        ),
        # Update WebChatMessage.message_id
        migrations.AlterField(
            model_name='webchatmessage',
            name='message_id',
            field=models.CharField(
                max_length=36,
                default=uuid.uuid4,
                unique=True,
                editable=False
            ),
        ),
    ]
