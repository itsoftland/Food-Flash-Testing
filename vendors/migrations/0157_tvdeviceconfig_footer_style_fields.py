from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0156_androiddevice_fcm_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="footer_font_size",
            field=models.CharField(
                choices=[
                    ("small", "Small"),
                    ("medium", "Medium"),
                    ("large", "Large"),
                    ("extra-large", "Extra Large"),
                ] + [(str(size), str(size)) for size in range(1, 101)],
                default="16",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="footer_text_color",
            field=models.CharField(default="#000000", max_length=7),
        ),
    ]
