# Generated manually for Dine Flash Buffet utility image links

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0160_alter_androidapk_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="utility",
            name="image_url",
            field=models.URLField(
                blank=True,
                help_text="Optional image URL (e.g. for Dine Flash Buffet utility display)",
                max_length=2048,
                null=True,
            ),
        ),
    ]
