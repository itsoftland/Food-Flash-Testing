from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0169_order_registration_batch_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="utility",
            name="approximate_service_time",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Hospital Flash: estimated service time in minutes",
            ),
        ),
        migrations.AddField(
            model_name="utility",
            name="department_type",
            field=models.CharField(
                choices=[
                    ("INDIVIDUAL", "Individual Department"),
                    ("GROUP", "Group Department"),
                ],
                default="INDIVIDUAL",
                help_text="Hospital Flash: individual department or group/package",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="utility",
            name="display_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Hospital Flash: sort order for department listings",
            ),
        ),
        migrations.AddField(
            model_name="utility",
            name="pre_announcement_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Hospital Flash: number of patients to pre-announce",
            ),
        ),
        migrations.AddField(
            model_name="utility",
            name="priority_prefix",
            field=models.CharField(
                blank=True,
                help_text="Hospital Flash: priority prefix (e.g. PL, PA, VIP)",
                max_length=4,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="utility",
            name="group_departments",
            field=models.ManyToManyField(
                blank=True,
                help_text="Hospital Flash: individual departments included in a group/package",
                related_name="included_in_groups",
                to="vendors.utility",
            ),
        ),
    ]
