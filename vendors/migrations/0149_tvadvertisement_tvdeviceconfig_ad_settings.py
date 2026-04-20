from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0148_tvdeviceconfig_display_columns_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TVAdvertisement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=120, null=True)),
                ("media_file", models.FileField(upload_to="tv_ads/")),
                ("media_type", models.CharField(choices=[("image", "Image"), ("video", "Video")], max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("admin_outlet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tv_advertisements", to="vendors.adminoutlet")),
            ],
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="ad_interval",
            field=models.PositiveSmallIntegerField(default=8),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="ad_position",
            field=models.CharField(choices=[("right", "Right Side"), ("left", "Left Side"), ("bottom", "Bottom Strip"), ("full_width", "Full Width Banner")], default="right", max_length=20),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="advertisements",
            field=models.ManyToManyField(blank=True, related_name="tv_configs", to="vendors.tvadvertisement"),
        ),
        migrations.AddField(
            model_name="tvdeviceconfig",
            name="enable_ads",
            field=models.BooleanField(default=False),
        ),
    ]
