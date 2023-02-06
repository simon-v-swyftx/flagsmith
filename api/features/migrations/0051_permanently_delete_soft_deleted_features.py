# Generated by Django 3.2.16 on 2023-01-18 15:14

from django.db import migrations

# Migration which only has a reverse direction to permanently delete any features and feature states
# that have been soft deleted
# NOTE: For some reason, when migrating backwards, this has incompatibilities with the previous migration to remove
# indexes (0050) so they cannot be run together in the same command. i.e. if the current state is at 0051 or above,
# running `python manage.py migrate features 0049` will fail with
# ValueError: Cannot query "FeatureState object (<id>)": Must be a "FeatureState" instance.
# To get around this, you can run each migration backwards individually, i.e.
# `python manage.py migrate features 0050 && python manage.py migrate features 0049`


def permanently_delete_features(apps, schema_editor):
    Feature = apps.get_model("features", "Feature")
    FeatureState = apps.get_model("features", "FeatureState")
    Feature.objects.filter(deleted_at__isnull=False).delete()
    FeatureState.objects.filter(deleted_at__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("features", "0050_remove_unique_indexes"),
    ]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop, reverse_code=permanently_delete_features
        ),
    ]