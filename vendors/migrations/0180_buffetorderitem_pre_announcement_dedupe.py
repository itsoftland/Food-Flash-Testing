from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0179_vendorconfig_completed_chat_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="buffetorderitem",
            name="pre_announcement_notified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Dine Flash Buffet: when this line last received a pre-announcement",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="buffetorderitem",
            name="pre_announcement_notified_distance",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Dine Flash Buffet: eligible-queue distance of the last "
                    "pre-announcement"
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="utility",
            name="pre_announcement_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Hospital Flash: number of patients to pre-announce. "
                    "Dine Flash Buffet: number of next station-queue items to "
                    "pre-announce."
                ),
            ),
        ),
    ]
