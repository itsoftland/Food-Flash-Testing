from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0168_hospital_flash_patient_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="registration_batch_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="archivedorder",
            name="registration_batch_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                editable=False,
                null=True,
            ),
        ),
    ]
