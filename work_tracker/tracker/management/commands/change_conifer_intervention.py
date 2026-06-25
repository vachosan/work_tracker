import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tracker.models import InterventionType, TreeIntervention
from tracker.pricing import apply_intervention_estimate


CONIFER_GENERA = (
    "Picea",
    "Pinus",
    "Abies",
    "Larix",
    "Thuja",
    "Taxus",
    "Juniperus",
    "Chamaecyparis",
    "Pseudotsuga",
    "Cedrus",
    "Tsuga",
    "Sequoiadendron",
    "Metasequoia",
    "Cupressus",
)

CONIFER_CZECH_TERMS = (
    "smrk",
    "borovice",
    "jedle",
    "modřín",
    "túje",
    "tuje",
    "zerav",
    "tis",
    "jalovec",
    "cypřišek",
    "douglaska",
    "cedr",
)

CSV_HEADERS = (
    "intervention_id",
    "tree_id",
    "project_id",
    "tree_identifier",
    "taxon",
    "taxon_latin",
    "taxon_czech",
    "old_intervention_type_id",
    "old_code",
    "old_name",
    "new_intervention_type_id",
    "new_code",
    "new_name",
    "status",
    "estimated_price_czk",
    "estimated_price_breakdown",
)


def _starts_with_known_genus(value):
    text = (value or "").strip().lower()
    if not text:
        return False
    for genus in CONIFER_GENERA:
        genus_lower = genus.lower()
        if text == genus_lower or text.startswith(f"{genus_lower} "):
            return True
    return False


def is_conifer_tree(tree):
    if _starts_with_known_genus(getattr(tree, "taxon_latin", "")):
        return True
    if _starts_with_known_genus(getattr(tree, "taxon", "")):
        return True

    czech = (getattr(tree, "taxon_czech", "") or "").strip().lower()
    return any(term in czech for term in CONIFER_CZECH_TERMS)


def _tree_identifier(tree):
    for attr in ("passport_code", "external_tree_id", "title"):
        value = getattr(tree, attr, None)
        if value:
            return value
    return str(tree.pk)


def _backup_row(intervention, to_type):
    tree = intervention.tree
    old_type = intervention.intervention_type
    return {
        "intervention_id": intervention.pk,
        "tree_id": tree.pk,
        "project_id": tree.project_id,
        "tree_identifier": _tree_identifier(tree),
        "taxon": tree.taxon,
        "taxon_latin": tree.taxon_latin,
        "taxon_czech": tree.taxon_czech,
        "old_intervention_type_id": old_type.pk,
        "old_code": old_type.code,
        "old_name": old_type.name,
        "new_intervention_type_id": to_type.pk,
        "new_code": to_type.code,
        "new_name": to_type.name,
        "status": intervention.status,
        "estimated_price_czk": intervention.estimated_price_czk,
        "estimated_price_breakdown": json.dumps(
            intervention.estimated_price_breakdown or {},
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


class Command(BaseCommand):
    help = "Safely change an intervention type from one code to another for conifers in one project."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, required=True)
        parser.add_argument("--from-code", default="S-RZ")
        parser.add_argument("--to-code", default="S-RB")
        parser.add_argument("--backup-dir")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview matching interventions. This is the default unless --confirm is passed.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Apply the change. Without this flag no data is modified.",
        )
        parser.add_argument(
            "--include-completed",
            action="store_true",
            help="Include completed interventions in addition to proposed interventions.",
        )

    def handle(self, *args, **options):
        project_id = options["project_id"]
        from_code = options["from_code"]
        to_code = options["to_code"]
        confirm = options["confirm"]
        include_completed = options["include_completed"]

        try:
            from_type = InterventionType.objects.get(code=from_code)
        except InterventionType.DoesNotExist as exc:
            raise CommandError(f"InterventionType with code {from_code!r} does not exist.") from exc

        try:
            to_type = InterventionType.objects.get(code=to_code)
        except InterventionType.DoesNotExist as exc:
            raise CommandError(f"InterventionType with code {to_code!r} does not exist.") from exc

        if from_type.pk == to_type.pk:
            raise CommandError("--from-code and --to-code resolve to the same InterventionType.")

        statuses = ["proposed"]
        if include_completed:
            statuses.append("completed")

        candidates = (
            TreeIntervention.objects.select_related("tree", "intervention_type")
            .filter(
                tree__project_id=project_id,
                intervention_type=from_type,
                status__in=statuses,
            )
            .order_by("tree_id", "id")
        )
        interventions = [item for item in candidates if is_conifer_tree(item.tree)]

        self.stdout.write(
            f"Project: {project_id}; from: {from_type.code} - {from_type.name}; "
            f"to: {to_type.code} - {to_type.name}; statuses: {', '.join(statuses)}"
        )
        self.stdout.write(f"Matched conifer interventions: {len(interventions)}")

        for item in interventions:
            tree = item.tree
            self.stdout.write(
                " | ".join(
                    [
                        f"intervention_id={item.pk}",
                        f"tree_id={tree.pk}",
                        f"tree_identifier={_tree_identifier(tree)}",
                        f"taxon={tree.taxon or ''}",
                        f"taxon_latin={tree.taxon_latin or ''}",
                        f"taxon_czech={tree.taxon_czech or ''}",
                        f"old={from_type.code} - {from_type.name}",
                        f"new={to_type.code} - {to_type.name}",
                        f"status={item.status}",
                        f"estimated_price_czk={item.estimated_price_czk}",
                        f"estimated_price_breakdown={item.estimated_price_breakdown or {}}",
                    ]
                )
            )

        if not confirm:
            self.stdout.write(self.style.WARNING("Dry run only. Pass --confirm to modify data."))
            return

        backup_dir = options.get("backup_dir")
        if not backup_dir:
            raise CommandError("--backup-dir is required when --confirm is passed.")

        backup_path = self._write_backup(backup_dir, project_id, from_type, to_type, interventions)
        self.stdout.write(f"CSV backup written: {backup_path}")

        with transaction.atomic():
            for intervention in interventions:
                intervention.intervention_type = to_type
                intervention.save(update_fields=["intervention_type", "updated_at"])
                apply_intervention_estimate(intervention)

        self.stdout.write(self.style.SUCCESS(f"Changed interventions: {len(interventions)}"))

    def _write_backup(self, backup_dir, project_id, from_type, to_type, interventions):
        path = Path(backup_dir)
        path.mkdir(parents=True, exist_ok=True)
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"change_conifer_intervention_project_{project_id}_"
            f"{from_type.code}_to_{to_type.code}_{timestamp}.csv"
        )
        backup_path = path / filename
        with backup_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for intervention in interventions:
                writer.writerow(_backup_row(intervention, to_type))
        return backup_path
