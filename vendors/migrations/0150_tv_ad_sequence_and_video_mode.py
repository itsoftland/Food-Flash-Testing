from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0149_tvadvertisement_tvdeviceconfig_ad_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="tvadvertisement",
            name="sequence",
            field=models.PositiveIntegerField(db_index=True, default=1),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="video_ad_mode",
            field=models.CharField(
                choices=[("play_full", "Play Full Video"), ("respect_interval", "Respect Ad Interval")],
                default="play_full",
                max_length=20,
            ),
        ),
    ]
