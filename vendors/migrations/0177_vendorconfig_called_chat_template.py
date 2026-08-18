# Generated for Hospital Flash Called chat-card template

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0176_vendorconfig_announcement_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorconfig",
            name="called_chat_template",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Hospital Flash: Called chat-card template. Use {department}. "
                    "Empty keeps the default: Please move to {department}."
                ),
            ),
        ),
    ]
