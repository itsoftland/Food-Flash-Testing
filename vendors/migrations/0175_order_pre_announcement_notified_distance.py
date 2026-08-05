from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0174_buffet_active_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="pre_announcement_notified_distance",
            field=models.PositiveIntegerField(
                blank=True,
                default=None,
                help_text=(
                    "Hospital Flash: queue distance at last pre-announcement; "
                    "allows re-notify when distance changes, blocks same-distance duplicates"
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="pre_announcement_notified_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Hospital Flash: set when a pre-announcement push was last sent",
                null=True,
            ),
        ),
    ]
