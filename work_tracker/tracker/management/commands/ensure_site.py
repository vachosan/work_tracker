import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site


class Command(BaseCommand):
    help = "Ensure django_site entry exists for SITE_ID."

    def handle(self, *args, **options):
        site_id = getattr(settings, "SITE_ID", 1)
        site = Site.objects.filter(id=site_id).first()

        domain = None
        if settings.DEBUG:
            domain = "127.0.0.1:8000"
        else:
            env_domain = os.environ.get("SITE_DOMAIN", "")
            if env_domain:
                domain = env_domain

        if site:
            if domain:
                site.domain = domain
            site.name = "ArboMap"
            site.save(update_fields=["domain", "name"])
            self.stdout.write(self.style.SUCCESS(f"Updated Site id={site_id} domain={site.domain}"))
            return

        if not domain:
            domain = "example.com"
            self.stdout.write(self.style.WARNING("SITE_DOMAIN not set; using example.com"))

        Site.objects.create(id=site_id, domain=domain, name="ArboMap")
        self.stdout.write(self.style.SUCCESS(f"Created Site id={site_id} domain={domain}"))
