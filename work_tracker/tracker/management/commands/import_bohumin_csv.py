import csv
import hashlib
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from tracker.models import (
    InterventionType,
    Project,
    ProjectTree,
    TreeAssessment,
    TreeIntervention,
    WorkRecord,
)


RE_MULTI_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def normalize_header(text: str) -> str:
    if text is None:
        return ""
    cleaned = text.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_float(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def parse_decimal_2(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def parse_multi_stem_dbh_cm(value):
    if value is None:
        return None, None
    original = str(value).strip()
    if not original:
        return None, None
    matches = RE_MULTI_NUM.findall(original)
    if not matches:
        return None, original
    values = []
    for item in matches:
        try:
            values.append(float(item.replace(",", ".")))
        except ValueError:
            continue
    if not values:
        return None, original
    return max(values), original


def parse_perspective(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower in ("a", "b", "c"):
        return lower
    numeric = parse_int(lower)
    if numeric == 1:
        return "a"
    if numeric == 2:
        return "b"
    if numeric == 3:
        return "c"
    return None


def build_description(import_note, multi_stem_text):
    note = import_note if import_note is not None else ""
    if not multi_stem_text:
        return note
    suffix = f"Kmeny (cm): {multi_stem_text}"
    if not note:
        return suffix
    if note.endswith("\n"):
        return f"{note}{suffix}"
    return f"{note}\n{suffix}"


def ensure_intervention_code(name):
    base = slugify(name or "") or "import"
    base = base[:20]
    existing = InterventionType.objects.filter(code=base).first()
    if not existing or existing.name == name:
        return base
    digest = hashlib.md5((name or "").encode("utf-8")).hexdigest()[:4]
    base_len = max(1, 20 - len(digest))
    candidate = f"{base[:base_len]}{digest}"
    if not InterventionType.objects.filter(code=candidate).exists():
        return candidate
    for counter in range(1, 10):
        suffix = f"{digest}{counter}"
        base_len = max(1, 20 - len(suffix))
        candidate = f"{base[:base_len]}{suffix}"
        if not InterventionType.objects.filter(code=candidate).exists():
            return candidate
    return candidate[:20]


class Command(BaseCommand):
    help = "Import Bohumin CSV into WorkRecord, ProjectTree, TreeAssessment (+ optional interventions)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--project-id", type=int, required=True)
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--delimiter", default=",")
        parser.add_argument("--encoding", default="utf-8-sig")
        parser.add_argument("--update", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-cadastre", action="store_true")
        parser.add_argument("--create-interventions", action="store_true")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        delimiter = options["delimiter"]
        encoding = options["encoding"]
        project_id = options["project_id"]
        user_id = options.get("user_id")
        update = options["update"]
        strict = options["strict"]
        dry_run = options["dry_run"]
        no_cadastre = options["no_cadastre"]
        create_interventions = options["create_interventions"]

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project {project_id} not found") from exc

        user = None
        if user_id:
            User = get_user_model()
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist as exc:
                raise CommandError(f"User {user_id} not found") from exc

        if no_cadastre:
            os.environ["ARBOMAP_DISABLE_CADASTRE_LOOKUP"] = "1"

        required_cols = {"p.č.", "taxon", "lat", "lon", "import_poznamka"}

        counts = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "assessments_created": 0,
            "assessments_updated": 0,
            "interventions_created": 0,
            "interventions_updated": 0,
            "errors": 0,
        }
        errors = []

        def record_error(row_num, external_id, message):
            counts["errors"] += 1
            if len(errors) < 10:
                errors.append(f"row {row_num} (p.č.={external_id}): {message}")

        def process_row(row, row_num):
            external_tree_id = (row.get("p.č.") or "").strip()
            if not external_tree_id:
                raise ValueError("Missing p.č.")

            taxon = (row.get("taxon") or "").strip()
            lat = parse_float(row.get("lat"))
            lon = parse_float(row.get("lon"))
            if lat is None or lon is None:
                raise ValueError("Missing or invalid lat/lon")

            dbh_value, dbh_original = parse_multi_stem_dbh_cm(
                row.get("průměr kmene (cm)")
            )
            import_note = row.get("import_poznamka")
            description = build_description(import_note, dbh_original)

            work_record = (
                WorkRecord.objects.filter(
                    project_id=project.pk,
                    external_tree_id=external_tree_id,
                ).first()
            )

            if work_record and not update:
                counts["skipped"] += 1
                return

            if not work_record:
                if dry_run:
                    counts["created"] += 1
                else:
                    work_record = WorkRecord.objects.create(
                        external_tree_id=external_tree_id,
                        taxon=taxon,
                        latitude=lat,
                        longitude=lon,
                        description=description,
                        project=project,
                    )
                    old_title = work_record.title
                    work_record.sync_title_from_identifiers()
                    if work_record.title != old_title:
                        work_record.save(update_fields=["title"])
                    counts["created"] += 1
            else:
                if dry_run:
                    counts["updated"] += 1
                else:
                    work_record.taxon = taxon
                    work_record.latitude = lat
                    work_record.longitude = lon
                    work_record.description = description
                    work_record.save(
                        update_fields=["taxon", "latitude", "longitude", "description"]
                    )
                    old_title = work_record.title
                    work_record.sync_title_from_identifiers()
                    if work_record.title != old_title:
                        work_record.save(update_fields=["title"])
                    counts["updated"] += 1

            if not dry_run and work_record:
                ProjectTree.objects.get_or_create(
                    project=project,
                    tree=work_record,
                    defaults={"added_by": user},
                )

            assessed_at = timezone.localdate()
            assessment_data = {
                "dbh_cm": dbh_value,
                "height_m": parse_float(row.get("výška (m)")),
                "crown_width_m": parse_decimal_2(row.get("průměr koruny (m)")),
                "health_state": parse_int(row.get("zdravotní stav")),
                "vitality": parse_int(row.get("fyziologická vitalita")),
                "physiological_age": parse_int(row.get("fyziologické stáří")),
                "stability": parse_int(row.get("stabilita")),
                "perspective": parse_perspective(row.get("perspektivita")),
            }

            if dry_run:
                existing_assessment = TreeAssessment.objects.filter(
                    work_record=work_record,
                    assessed_at=assessed_at,
                ).exists() if work_record else False
                if existing_assessment:
                    counts["assessments_updated"] += 1
                else:
                    counts["assessments_created"] += 1
            else:
                assessment, created_assessment = TreeAssessment.objects.get_or_create(
                    work_record=work_record,
                    assessed_at=assessed_at,
                    defaults=assessment_data,
                )
                if created_assessment:
                    counts["assessments_created"] += 1
                else:
                    for key, value in assessment_data.items():
                        setattr(assessment, key, value)
                    assessment.save()
                    counts["assessments_updated"] += 1

            if create_interventions:
                tech = (row.get("technologie pěstebního opatření") or "").strip()
                if tech:
                    urgency = parse_int(row.get("naléhavost"))
                    if urgency is None or urgency not in (0, 1, 2, 3):
                        urgency = 2

                    if dry_run:
                        counts["interventions_created"] += 1
                    else:
                        intervention_type = (
                            InterventionType.objects.filter(name=tech).first()
                        )
                        if not intervention_type:
                            code = ensure_intervention_code(tech)
                            intervention_type = InterventionType.objects.create(
                                code=code,
                                name=tech,
                                category="import",
                                is_active=True,
                            )

                        intervention, created_intervention = TreeIntervention.objects.get_or_create(
                            tree=work_record,
                            intervention_type=intervention_type,
                            status="proposed",
                            defaults={
                                "urgency": urgency,
                                "description": import_note or "",
                                "created_by": user,
                            },
                        )
                        if created_intervention:
                            counts["interventions_created"] += 1
                        else:
                            intervention.urgency = urgency
                            intervention.description = import_note or ""
                            if user:
                                intervention.created_by = user
                            intervention.save(
                                update_fields=["urgency", "description", "created_by"]
                                if user
                                else ["urgency", "description"]
                            )
                            counts["interventions_updated"] += 1

        def run_import():
            with open(csv_path, "r", encoding=encoding, newline="") as handle:
                dict_reader = csv.DictReader(handle, delimiter=delimiter)
                if not dict_reader.fieldnames:
                    raise CommandError("CSV is empty")
                normalized_headers = [normalize_header(h) for h in dict_reader.fieldnames]
                dict_reader.fieldnames = normalized_headers
                missing = required_cols.difference(set(dict_reader.fieldnames))
                if missing:
                    raise CommandError(
                        "Missing required columns: " + ", ".join(sorted(missing))
                    )

                for idx, row in enumerate(dict_reader, start=2):
                    try:
                        process_row(row, idx)
                    except Exception as exc:
                        if strict:
                            raise
                        external_id = (row.get("p.č.") or "").strip()
                        record_error(idx, external_id, str(exc))

        if strict and not dry_run:
            with transaction.atomic():
                run_import()
        else:
            run_import()

        self.stdout.write(
            "Created: {created}, Updated: {updated}, Skipped: {skipped}, "
            "Assessments Created: {assessments_created}, Assessments Updated: {assessments_updated}, "
            "Interventions Created: {interventions_created}, Interventions Updated: {interventions_updated}, "
            "Errors: {errors}".format(**counts)
        )
        if errors:
            self.stdout.write("First errors:")
            for err in errors:
                self.stdout.write(err)
