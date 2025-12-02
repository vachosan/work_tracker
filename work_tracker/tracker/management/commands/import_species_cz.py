import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from tracker.models import Species


class Command(BaseCommand):
    help = "Importuje české dřeviny z tracker/data/species_cz_trees_shrubs.csv"

    def handle(self, *args, **options):
        data_path = Path(__file__).resolve().parents[2] / "data" / "species_cz_trees_shrubs.csv"
        created = 0
        updated = 0

        with data_path.open(encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                latin = (row.get("NameLatFinal") or "").strip()
                if not latin:
                    continue
                czech = (row.get("NameCzFinal") or "").strip()
                type_value = (row.get("Type") or "").strip().lower()

                _, was_created = Species.objects.update_or_create(
                    latin_name=latin,
                    defaults={"czech_name": czech, "type": type_value},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(f"Created {created}, updated {updated}")
