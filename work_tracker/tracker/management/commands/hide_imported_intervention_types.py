import re

from django.core.management.base import BaseCommand

from tracker.models import InterventionType


CANONICAL_CODE_PATTERN = re.compile(r"^[A-Z]{1,3}-[A-Z0-9]{1,8}$")


class Command(BaseCommand):
    help = "Hide imported/duplicate intervention types from selection dropdown."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show what would be hidden without updating records.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        candidates = []
        canonical_examples = []
        candidate_examples = []
        for item in InterventionType.objects.all():
            code = (item.code or "").strip()
            name = (item.name or "").strip()
            if CANONICAL_CODE_PATTERN.match(code):
                if len(canonical_examples) < 20:
                    canonical_examples.append(code)
                continue
            norm_code = code.lower()
            norm_name = name.lower()

            match_lowercase = re.search(r"[a-z]", code or "") is not None
            match_dash_count = (code.count("-") if code else 0) >= 2
            match_prefix = norm_code.startswith("pb-") or norm_code.startswith("legacy")
            match_name = "," in norm_name

            if match_lowercase or match_dash_count or match_prefix or match_name:
                candidates.append(item)
                if len(candidate_examples) < 20:
                    candidate_examples.append(code or "(bez kódu)")

        found = len(candidates)
        already_hidden = 0
        hidden = 0
        for item in candidates:
            if not item.is_selectable:
                already_hidden += 1
                continue
            if not dry_run:
                item.is_selectable = False
                item.save(update_fields=["is_selectable"])
            hidden += 1

        self.stdout.write(self.style.SUCCESS(f"Found candidates: {found}"))
        self.stdout.write(self.style.SUCCESS(f"Hidden: {hidden}"))
        self.stdout.write(self.style.SUCCESS(f"Already hidden: {already_hidden}"))
        if candidate_examples:
            self.stdout.write("Candidates (first 20):")
            for code in candidate_examples:
                self.stdout.write(f"- {code}")
        if canonical_examples:
            self.stdout.write("Canonical (first 20):")
            for code in canonical_examples:
                self.stdout.write(f"- {code}")
