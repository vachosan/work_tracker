from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0033_shrubassessment_assessed_at_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="workrecord",
            name="hedge_line",
            field=models.JSONField(
                blank=True,
                null=True,
                verbose_name="Osa živého plotu (GeoJSON LineString)",
            ),
        ),
    ]
