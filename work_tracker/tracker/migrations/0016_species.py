from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0015_add_taxon_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Species",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("latin_name", models.CharField(max_length=255)),
                ("czech_name", models.CharField(blank=True, max_length=255)),
                ("type", models.CharField(choices=[("strom", "Strom"), ("keř", "Keř")], max_length=10)),
            ],
            options={
                "ordering": ["latin_name"],
            },
        ),
        migrations.AddIndex(
            model_name="species",
            index=models.Index(fields=["latin_name"], name="tracker_spec_latin_name_idx"),
        ),
        migrations.AddIndex(
            model_name="species",
            index=models.Index(fields=["czech_name"], name="tracker_spec_czech_name_idx"),
        ),
    ]
