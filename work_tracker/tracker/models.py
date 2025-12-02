import string

from django.db import models
from django.utils import timezone
from django.conf import settings


PHYSIOLOGICAL_AGE_CHOICES = [
    (1, "1 – mladý jedinec ve fázi ujímání"),
    (2, "2 – aklimatizovaný mladý strom"),
    (3, "3 – dospívající jedinec"),
    (4, "4 – dospělý jedinec"),
    (5, "5 – senescentní jedinec"),
]

VITALITY_CHOICES = [
    (1, "1 – výborná až mírně snížená"),
    (2, "2 – zřetelně snížená"),
    (3, "3 – výrazně snížená"),
    (4, "4 – zbytková"),
    (5, "5 – suchý (mrtvý) strom"),
]

HEALTH_STATE_CHOICES = [
    (1, "1 – výborný až dobrý"),
    (2, "2 – zhoršený"),
    (3, "3 – výrazně zhoršený"),
    (4, "4 – silně narušený"),
    (5, "5 – kritický / rozpadlý strom"),
]

STABILITY_CHOICES = [
    (1, "1 – výborná až dobrá (nenarušená)"),
    (2, "2 – zhoršená"),
    (3, "3 – výrazně zhoršená"),
    (4, "4 – silně narušená"),
    (5, "5 – kritická"),
]

PERSPECTIVE_CHOICES = [
    ("a", "a – dlouhodobě perspektivní"),
    ("b", "b – krátkodobě perspektivní"),
    ("c", "c – neperspektivní"),
]

BASE36_ALPHABET = string.digits + string.ascii_uppercase


def int_to_base36(n: int) -> str:
    if n < 0:
        raise ValueError("int_to_base36: n must be non-negative")
    if n == 0:
        return "0"
    digits = []
    base = 36
    while n:
        n, rem = divmod(n, base)
        digits.append(BASE36_ALPHABET[rem])
    return "".join(reversed(digits))


class Project(models.Model):
    name = models.CharField(max_length=200, verbose_name="Název projektu")
    description = models.TextField(verbose_name="Popis projektu", blank=True)
    is_closed = models.BooleanField(default=False, verbose_name="Uzavřený projekt")

    def __str__(self):
        return self.name


class Species(models.Model):
    latin_name = models.CharField(max_length=255)
    czech_name = models.CharField(max_length=255, blank=True)
    type = models.CharField(
        max_length=10,
        choices=(
            ("strom", "Strom"),
            ("keř", "Keř"),
        ),
    )

    class Meta:
        ordering = ["latin_name"]
        indexes = [
            models.Index(fields=["latin_name"]),
            models.Index(fields=["czech_name"]),
        ]

    def __str__(self):
        if self.czech_name:
            return f"{self.czech_name} ({self.latin_name})"
        return self.latin_name


class WorkRecord(models.Model):
    title = models.CharField(max_length=200, blank=True)
    external_tree_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Číslo stromu (externí)",
        help_text="Číslo stromu z papírové inventarizace, cedulek nebo jiného systému.",
    )
    taxon = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Taxon",
        help_text="Botanický název stromu.",
    )
    taxon_czech = models.CharField(max_length=255, blank=True)
    taxon_latin = models.CharField(max_length=255, blank=True)
    taxon_gbif_key = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_records",
        verbose_name="Projekt",
    )

    latitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Zeměpisná šířka (latitude, např. 49.684)",
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        help_text="Zeměpisná délka (longitude, např. 18.676)",
    )

    # start_time = models.DateTimeField(default=timezone.now)
    # end_time = models.DateTimeField(null=True, blank=True)
    # note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def generate_internal_code(self) -> str | None:
        """
        Generate a short internal identifier from the primary key in base36.

        pk=1   -> "1"
        pk=35  -> "Z"
        pk=36  -> "10"
        pk=1234 -> "YA"
        """
        if not self.pk:
            return None
        return int_to_base36(int(self.pk))

    def sync_title_from_identifiers(self):
        """
        Ensure `title` is always usable for display/export:

        - If external_tree_id is set, title mirrors it.
        - Else if title already has a value (legacy data), leave it unchanged.
        - Else, derive a short internal code based on the PK.
        """
        if self.external_tree_id:
            # Prefer explicit external id for all user-facing purposes
            self.title = self.external_tree_id
            return

        # No external id; if there is already some title (old data),
        # treat it as user-defined / legacy external code and do not overwrite it.
        if self.title:
            return

        # No external id and no existing title -> generate internal short code
        internal_code = self.generate_internal_code()
        if internal_code:
            self.title = internal_code

    def __str__(self):
        # Primary display: title (which mirrors external_tree_id or legacy title)
        if self.title:
            return self.title

        # Fallback: short internal code if pk exists
        internal_code = self.generate_internal_code()
        if internal_code:
            return internal_code

        return "WorkRecord (unsaved)"

    @property
    def latest_assessment(self):
        """
        Vrátí nejnovější hodnocení stromu (nebo None, pokud neexistuje).
        Řadíme podle assessed_at a id.
        """
        return self.assessments.order_by("-assessed_at", "-id").first()


class TreeAssessment(models.Model):
    work_record = models.ForeignKey(
        "WorkRecord",
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="Pracovní záznam",
    )

    assessed_at = models.DateField(
        default=timezone.now,
        verbose_name="Datum hodnocení",
    )

    dbh_cm = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Průměr kmene (DBH) [cm]",
        help_text="Průměr kmene v centimetrech v měřické výšce.",
    )

    height_m = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Výška stromu [m]",
        help_text="Výška stromu v metrech.",
    )

    physiological_age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=PHYSIOLOGICAL_AGE_CHOICES,
        verbose_name="Fyziologické stáří",
    )

    vitality = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=VITALITY_CHOICES,
        verbose_name="Vitalita",
    )

    health_state = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=HEALTH_STATE_CHOICES,
        verbose_name="Zdravotní stav",
    )

    stability = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=STABILITY_CHOICES,
        verbose_name="Stabilita",
    )

    perspective = models.CharField(
        max_length=1,
        null=True,
        blank=True,
        choices=PERSPECTIVE_CHOICES,
        verbose_name="Perspektiva stromu",
    )

    class Meta:
        verbose_name = "Hodnocení stromu"
        verbose_name_plural = "Hodnocení stromů"

    def __str__(self):
        return f"Hodnocení pro WorkRecord #{self.work_record_id}"


class PhotoDocumentation(models.Model):
    work_record = models.ForeignKey(
        "WorkRecord", related_name="photos", on_delete=models.CASCADE
    )
    photo = models.ImageField(
        upload_to="photos/", null=True, blank=True, default="photos/default.jpg"
    )
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.description or f"Photo #{self.id}"


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        FOREMAN = "FOREMAN", "Stavbyvedoucí"
        WORKER = "WORKER", "Dělník"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)

    class Meta:
        unique_together = ("user", "project")

    def __str__(self):
        return f"{self.user} · {self.project} · {self.role}"
