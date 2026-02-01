from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0035_treeassessment_stem_circumference_cm"),
    ]

    operations = [
        migrations.AddField(
            model_name="treeassessment",
            name="stem_diameters_cm_list",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Průměry kmenů [cm] (CSV)",
            ),
        ),
        migrations.AddField(
            model_name="treeassessment",
            name="stem_circumferences_cm_list",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Obvody kmenů [cm] (CSV)",
            ),
        ),
    ]
