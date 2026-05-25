from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0164_utility_food_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="utility",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="Optional description for Dine Flash Buffet utilities",
                null=True,
            ),
        ),
    ]
