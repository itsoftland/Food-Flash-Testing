# Recreates vendors_tvdeviceconfig_utilities when the DB drifted (e.g. migration 0121
# marked applied but the M2M table was never created). MySQL error 1146.

from django.db import migrations


def ensure_tvdeviceconfig_utilities_m2m(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = 'vendors_tvdeviceconfig_utilities'
            """
        )
        if cursor.fetchone()[0]:
            return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE `vendors_tvdeviceconfig_utilities` (
                `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
                `tvdeviceconfig_id` bigint NOT NULL,
                `utility_id` bigint NOT NULL
            )
            """
        )
        cursor.execute(
            """
            ALTER TABLE `vendors_tvdeviceconfig_utilities`
            ADD CONSTRAINT `vendors_tvdeviceconfig_u_tvdeviceconfig_id_utilit_3b7b7113_uniq`
            UNIQUE (`tvdeviceconfig_id`, `utility_id`)
            """
        )
        cursor.execute(
            """
            ALTER TABLE `vendors_tvdeviceconfig_utilities`
            ADD CONSTRAINT `vendors_tvdeviceconf_tvdeviceconfig_id_f14ecfa6_fk_vendors_t`
            FOREIGN KEY (`tvdeviceconfig_id`) REFERENCES `vendors_tvdeviceconfig` (`id`)
            """
        )
        cursor.execute(
            """
            ALTER TABLE `vendors_tvdeviceconfig_utilities`
            ADD CONSTRAINT `vendors_tvdeviceconf_utility_id_645beb29_fk_vendors_u`
            FOREIGN KEY (`utility_id`) REFERENCES `vendors_utility` (`id`)
            """
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0153_alter_tvadvertisement_options"),
    ]

    operations = [
        migrations.RunPython(ensure_tvdeviceconfig_utilities_m2m, noop_reverse),
    ]
