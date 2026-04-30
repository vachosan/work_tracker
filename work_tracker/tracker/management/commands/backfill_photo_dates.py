from django.core.management.base import BaseCommand

from tracker.models import PhotoDocumentation, parse_photo_date_from_description


class Command(BaseCommand):
    help = "Backfill PhotoDocumentation.photo_date from the leading date in description."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report changes without saving them.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        scanned = 0
        changed = 0
        parsed_count = 0
        null_count = 0

        queryset = PhotoDocumentation.objects.only("id", "description", "photo_date").order_by("id")
        for photo in queryset.iterator(chunk_size=500):
            scanned += 1
            parsed_date = parse_photo_date_from_description(photo.description)
            if parsed_date:
                parsed_count += 1
            else:
                null_count += 1

            if photo.photo_date == parsed_date:
                continue

            changed += 1
            if not dry_run:
                PhotoDocumentation.objects.filter(pk=photo.pk).update(photo_date=parsed_date)

        suffix = " (dry run)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {scanned} photos, changed {changed}, parsed {parsed_count}, null {null_count}{suffix}."
            )
        )
