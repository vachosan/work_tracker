# Generated manually for photo date filtering.

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0043_interventiontype_is_selectable"),
    ]

    operations = [
        migrations.AddField(
            model_name="photodocumentation",
            name="photo_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="photodocumentation",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
    ]
