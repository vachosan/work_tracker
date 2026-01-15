from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0027_simplify_treeintervention_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="workrecord",
            name="parcel_number",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="cadastral_area_code",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="cadastral_area_name",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="municipality_code",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="municipality_name",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="lv_number",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="cad_lookup_status",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="workrecord",
            name="cad_lookup_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
