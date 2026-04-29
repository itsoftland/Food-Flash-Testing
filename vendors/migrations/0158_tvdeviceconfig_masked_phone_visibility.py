from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0157_tvdeviceconfig_footer_style_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="show_partially_masked_phone_number",
            field=models.BooleanField(default=False),
        ),
    ]
