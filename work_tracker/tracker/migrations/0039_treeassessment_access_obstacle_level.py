from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0038_rename_tracker_ruianc_cadastr_536f47_idx_tracker_rui_cadastr_985d1c_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="treeassessment",
            name="access_obstacle_level",
            field=models.PositiveSmallIntegerField(
                default=0,
                choices=[
                    (0, "Volné stanoviště"),
                    (1, "Pomístní překážky (+30 %)"),
                    (2, "Omezená přístupnost / plné spouštění (+60 %)"),
                ],
                verbose_name="Překážky (NOO)",
                help_text="Kategorie přístupnosti/překážek pro odhad ceny.",
            ),
        ),
    ]
