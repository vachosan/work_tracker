from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0036_treeassessment_stem_lists"),
    ]

    operations = [
        migrations.AddField(
            model_name="treeassessment",
            name="mistletoe_level",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, "R – vzácné (do 5 % objemu koruny)"),
                    (2, "O – příležitostné (6–10 % objemu koruny)"),
                    (3, "F – časté (11–30 % objemu koruny)"),
                    (4, "A – hojné (31–50 % objemu koruny)"),
                    (5, "D – dominantní (> 50 % objemu koruny)"),
                ],
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ],
                verbose_name="Zastoupení jmelí",
            ),
        ),
    ]
