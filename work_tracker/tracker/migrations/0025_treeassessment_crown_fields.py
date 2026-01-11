from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


def backfill_crown_area_m2(apps, schema_editor):
    TreeAssessment = apps.get_model("tracker", "TreeAssessment")
    for assessment in TreeAssessment.objects.all().iterator():
        width = assessment.crown_width_m
        height = assessment.height_m
        if width is None or height is None or width <= 0 or height <= 0:
            area = None
        else:
            width_dec = Decimal(str(width))
            height_dec = Decimal(str(height))
            area = (width_dec * height_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        TreeAssessment.objects.filter(pk=assessment.pk).update(crown_area_m2=area)


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0024_populate_system_dataset"),
    ]

    operations = [
        migrations.AddField(
            model_name="treeassessment",
            name="crown_width_m",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Šířka koruny [m]"),
        ),
        migrations.AddField(
            model_name="treeassessment",
            name="crown_area_m2",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True, verbose_name="Plocha koruny [m²]"),
        ),
        migrations.RunPython(backfill_crown_area_m2, migrations.RunPython.noop),
    ]
