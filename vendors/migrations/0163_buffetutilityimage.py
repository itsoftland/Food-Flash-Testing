from django.core.validators import FileExtensionValidator
from django.db import migrations, models
import django.db.models.deletion


def migrate_legacy_buffet_images(apps, schema_editor):
    Utility = apps.get_model("vendors", "Utility")
    BuffetUtilityImage = apps.get_model("vendors", "BuffetUtilityImage")
    for utility in Utility.objects.exclude(buffet_utility_image="").exclude(
        buffet_utility_image__isnull=True
    ):
        if not utility.buffet_utility_image:
            continue
        if BuffetUtilityImage.objects.filter(utility_id=utility.id).exists():
            continue
        BuffetUtilityImage.objects.create(
            utility_id=utility.id,
            image=utility.buffet_utility_image,
            sort_order=0,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0162_replace_utility_image_url_with_buffet_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuffetUtilityImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        upload_to="buffet_utilities/%Y/%m",
                        validators=[
                            FileExtensionValidator(
                                allowed_extensions=[
                                    "jpg",
                                    "jpeg",
                                    "png",
                                    "gif",
                                    "webp",
                                ]
                            )
                        ],
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "utility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buffet_images",
                        to="vendors.utility",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.RunPython(
            migrate_legacy_buffet_images,
            migrations.RunPython.noop,
        ),
    ]
