from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0163_buffetutilityimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="utility",
            name="food_type",
            field=models.CharField(
                blank=True,
                choices=[("veg", "Veg"), ("non_veg", "Non Veg")],
                help_text="Veg or Non Veg (Dine Flash Buffet only)",
                max_length=10,
                null=True,
            ),
        ),
    ]
