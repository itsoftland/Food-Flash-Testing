from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0170_hospital_flash_utility_department_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="pre_announcement_notified_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Hospital Flash: set when pre-announcement push was sent",
                null=True,
            ),
        ),
    ]
