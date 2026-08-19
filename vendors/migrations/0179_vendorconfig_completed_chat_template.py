# Generated for Hospital Flash Completed chat-card template

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0178_vendorconfig_pre_announcement_chat_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="completed_chat_template",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Hospital Flash: Completed chat-card template. Optional {department}. "
                    "Empty keeps the default: Thank You."
                ),
            ),
        ),
    ]
