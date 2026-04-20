from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0150_tv_ad_sequence_and_video_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="footer_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="footer_texts",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="header_font_size",
            field=models.CharField(
                choices=[("small", "Small"), ("medium", "Medium"), ("large", "Large"), ("extra-large", "Extra Large")],
                default="large",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="header_font_style",
            field=models.CharField(
                choices=[("regular", "Regular"), ("medium", "Medium"), ("bold", "Bold")],
                default="bold",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="header_text_color",
            field=models.CharField(default="#000000", max_length=7),
        ),
    ]
