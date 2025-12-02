from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0014_workrecord_taxon"),
    ]

    operations = [
        migrations.AddField(
            model_name="workrecord",
            name="taxon_czech",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workrecord",
            name="taxon_latin",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workrecord",
            name="taxon_gbif_key",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
