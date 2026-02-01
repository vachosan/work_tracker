from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0034_workrecord_hedge_line"),
    ]

    operations = [
        migrations.AddField(
            model_name="treeassessment",
            name="stem_circumference_cm",
            field=models.FloatField(
                blank=True,
                help_text="Obvod kmene v centimetrech v měřické výšce.",
                null=True,
                verbose_name="Obvod kmene [cm]",
            ),
        ),
    ]
