from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0161_utility_image_url"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="utility",
            name="image_url",
        ),
        migrations.AddField(
            model_name="utility",
            name="buffet_utility_image",
            field=models.ImageField(
                blank=True,
                help_text="Uploaded image for Dine Flash Buffet utility display",
                null=True,
                upload_to="buffet_utilities/%Y/%m",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"]
                    )
                ],
            ),
        ),
    ]