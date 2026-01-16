from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from tracker.models import (
    RuianCadastralArea,
    RuianCadastralAreaMunicipality,
    RuianMunicipality,
    WorkRecord,
)


class Command(BaseCommand):
    help = "Populate WorkRecord cadastral_area_name and municipality_name from local RUIAN tables."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"] or None
        dry_run = options["dry_run"]

        cadastral_names = dict(
            RuianCadastralArea.objects.values_list("code", "name")
        )
        municipality_names = dict(
            RuianMunicipality.objects.values_list("code", "name")
        )

        mapping = {}
        for cadastral_id, municipality_id in RuianCadastralAreaMunicipality.objects.order_by(
            "cadastral_area_id", "municipality_id"
        ).values_list("cadastral_area_id", "municipality_id"):
            if cadastral_id not in mapping:
                mapping[cadastral_id] = municipality_id

        qs = WorkRecord.objects.filter(
            cadastral_area_code__isnull=False
        ).exclude(cadastral_area_code="")
        qs = qs.filter(
            Q(cadastral_area_name__isnull=True)
            | Q(cadastral_area_name="")
            | Q(municipality_name__isnull=True)
            | Q(municipality_name="")
        )
        if limit:
            qs = qs[:limit]

        to_update = []
        for record in qs:
            cadastral_code = record.cadastral_area_code
            cadastral_name = cadastral_names.get(cadastral_code)
            municipality_code = mapping.get(cadastral_code)
            municipality_name = municipality_names.get(municipality_code) if municipality_code else None

            changed = False
            if cadastral_name and not record.cadastral_area_name:
                record.cadastral_area_name = cadastral_name
                changed = True
            if municipality_name and not record.municipality_name:
                record.municipality_name = municipality_name
                changed = True
            if changed:
                to_update.append(record)

        if dry_run:
            self.stdout.write(f"Would update {len(to_update)} records")
            return

        with transaction.atomic():
            WorkRecord.objects.bulk_update(
                to_update, ["cadastral_area_name", "municipality_name"], batch_size=500
            )

        self.stdout.write(f"Updated {len(to_update)} records")
