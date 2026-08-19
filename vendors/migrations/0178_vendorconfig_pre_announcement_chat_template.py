# Generated for Hospital Flash pre-announcement chat-card template

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0177_vendorconfig_called_chat_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="pre_announcement_chat_template",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Hospital Flash: Pre-announcement chat-card template. Use {minutes}. "
                    "Empty keeps the default: You will be called in {minutes} minute(s)."
                ),
            ),
        ),
    ]
