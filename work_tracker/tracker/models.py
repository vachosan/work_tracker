import logging
import math
import string
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings

# models module for ArboMap tracker app
logger = logging.getLogger(__name__)

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

    trees = models.ManyToManyField(
        "WorkRecord",
        through="ProjectTree",
        related_name="projects",
        blank=True,
    )


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
    created_at = models.DateTimeField(auto_now_add=True)
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
    parcel_number = models.CharField(max_length=64, blank=True, null=True)
    cadastral_area_code = models.CharField(max_length=32, blank=True, null=True)
    cadastral_area_name = models.CharField(max_length=128, blank=True, null=True)
    municipality_code = models.CharField(max_length=32, blank=True, null=True)
    municipality_name = models.CharField(max_length=128, blank=True, null=True)
    lv_number = models.CharField(max_length=32, blank=True, null=True)
    cad_lookup_status = models.CharField(max_length=16, blank=True, null=True)
    cad_lookup_at = models.DateTimeField(blank=True, null=True)

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

    crown_width_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Šířka koruny [m]",
    )

    crown_area_m2 = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Plocha koruny [m²]",
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

    def _compute_crown_area_m2(self):
        width = self.crown_width_m
        height = self.height_m
        if width is None or height is None:
            return None
        if width <= 0 or height <= 0:
            return None
        width_dec = width if isinstance(width, Decimal) else Decimal(str(width))
        height_dec = Decimal(str(height))
        return (width_dec * height_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.crown_area_m2 = self._compute_crown_area_m2()
        super().save(*args, **kwargs)


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.photo:
            return
        try:
            from .views import get_photo_thumbnail
        except Exception:
            return
        get_photo_thumbnail(self)


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Zadavatel"
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


class Dataset(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE", "Soukromý"
        PUBLIC = "PUBLIC", "Veřejný"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )
    allow_public_observations = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_datasets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_system"],
                condition=models.Q(is_system=True),
                name="unique_system_dataset",
            )
        ]

    def __str__(self):
        return self.name


class DatasetTree(models.Model):
    dataset = models.ForeignKey(
        "Dataset",
        on_delete=models.CASCADE,
        related_name="dataset_trees",
    )
    tree = models.ForeignKey(
        "WorkRecord",
        on_delete=models.CASCADE,
        related_name="in_datasets",
    )

    class Meta:
        unique_together = ("dataset", "tree")
        indexes = [
            models.Index(fields=["tree"]),
        ]


class ProjectTree(models.Model):
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="project_trees",
    )
    tree = models.ForeignKey(
        "WorkRecord",
        on_delete=models.CASCADE,
        related_name="tree_projects",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_tree_additions",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "tree")
        indexes = [
            models.Index(fields=["project", "tree"]),
            models.Index(fields=["tree"]),
        ]


INTERVENTION_STATUS_CHOICES = [
    ("proposed", "Navrženo"),
    ("done_pending_owner", "Hotovo – čeká na potvrzení"),
    ("completed", "Potvrzeno"),
]

URGENCY_CHOICES = [
    (0, "0 – okamžitě, riziko z prodlení"),
    (1, "1 – první etapa prací"),
    (2, "2 – druhá etapa prací"),
    (3, "3 – třetí etapa prací"),
]


class InterventionType(models.Model):
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Kód technologie",
        default="legacy",
    )
    name = models.CharField(max_length=255, verbose_name="Název technologie")
    category = models.CharField(max_length=100, blank=True, verbose_name="Kategorie")
    description = models.TextField(blank=True, verbose_name="Popis")
    note_required = models.BooleanField(default=False, verbose_name="Vyžaduje doplnění poznámky")
    note_hint = models.TextField(blank=True, verbose_name="Pokyny k doplnění")
    is_active = models.BooleanField(default=True, verbose_name="Aktivní")
    order = models.PositiveIntegerField(default=0, verbose_name="Pořadí")

    class Meta:
        verbose_name = "Typ zásahu"
        verbose_name_plural = "Typy zásahů"
        ordering = ["order", "name"]

    def __str__(self):
        if self.code:
            return f"{self.code} – {self.name}"
        return self.name


class TreeIntervention(models.Model):
    def mark_approved(self):
        self.status = "done_pending_owner"
        if getattr(self, "approved_at", None) is None:
            self.approved_at = timezone.now()
        self.save()

    def mark_handed_over_for_check(self):
        self.status = "done_pending_owner"
        if getattr(self, "handed_over_for_check_at", None) is None:
            self.handed_over_for_check_at = timezone.now()
        self.save()

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Schváleno dne",
    )
    handed_over_for_check_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Předáno ke kontrole dne",
    )
    tree = models.ForeignKey(
        "WorkRecord",
        related_name="interventions",
        on_delete=models.CASCADE,
        verbose_name="Strom",
    )
    intervention_type = models.ForeignKey(
        "InterventionType",
        on_delete=models.PROTECT,
        verbose_name="Typ zásahu",
    )
    description = models.TextField(blank=True, verbose_name="Popis zásahu")
    urgency = models.IntegerField(
        choices=URGENCY_CHOICES,
        default=2,
        verbose_name="Naléhavost",
    )
    status = models.CharField(
        max_length=32,
        choices=INTERVENTION_STATUS_CHOICES,
        default="proposed",
        verbose_name="Stav zásahu",
    )
    status_note = models.TextField(blank=True, verbose_name="Poznámka ke stavu")
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Termín zásahu",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_interventions",
        verbose_name="Navrhl",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_interventions",
        verbose_name="Zodpovědný",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Vytvořeno")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Aktualizováno")

    class Meta:
        verbose_name = "Zásah na stromě"
        verbose_name_plural = "Zásahy na stromě"
        ordering = ["status", "urgency", "due_date", "id"]

    def __str__(self):
        status = self.get_status_display() if self.status else ""
        parts = [str(self.tree)]
        if self.intervention_type:
            parts.append(str(self.intervention_type))
        if status:
            parts.append(status)
        return " · ".join(parts)


def get_workrecord_lonlat(record: "WorkRecord"):
    if record.latitude is None or record.longitude is None:
        return None
    try:
        return float(record.longitude), float(record.latitude)
    except (TypeError, ValueError):
        return None


CUZK_CP_WFS_ENDPOINT = "https://services.cuzk.gov.cz/wfs/inspire-cp-wfs.asp"
# TODO: Verify typename + available fields from GetCapabilities:
# https://services.cuzk.gov.cz/wfs/inspire-cp-wfs.asp?service=WFS&request=GetCapabilities
CUZK_CP_WFS_TYPENAME = "cp:CadastralParcel"


def _debug_log(message: str, **extra):
    if not settings.DEBUG:
        return
    logger.debug(message, extra=extra if extra else None)


def _http_get(url: str, timeout_s: int = 3, retries: int = 1) -> tuple[int, str | None, bytes]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urlopen(url, timeout=timeout_s) as resp:
                status = resp.getcode()
                content_type = resp.headers.get("Content-Type")
                return status, content_type, resp.read()
        except URLError as err:
            last_err = err
            _debug_log("cad_lookup http error", url=url, attempt=attempt, error=str(err))
            if attempt >= retries:
                raise
    if last_err:
        raise last_err
    raise URLError("cad_lookup http error")


def _build_wfs_url(bbox: tuple[float, float, float, float], version: str) -> str:
    minx, miny, maxx, maxy = bbox
    count = 1
    params = {
        "SERVICE": "WFS",
        "REQUEST": "GetFeature",
        "VERSION": version,
        "TYPENAMES": CUZK_CP_WFS_TYPENAME,
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
    }
    if version == "2.0.0":
        params["COUNT"] = count
    else:
        params["MAXFEATURES"] = count
    return f"{CUZK_CP_WFS_ENDPOINT}?{urlencode(params)}"


def _log_cad_response(url: str, status: int, content_type: str | None, payload: bytes) -> None:
    text = payload.decode("utf-8", errors="replace")
    root_tag = None
    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(payload)
        root_tag = root.tag.split("}")[-1]
    except Exception:
        root = None

    is_exception = root_tag in ("ServiceExceptionReport", "ExceptionReport")
    is_feature_collection = root_tag == "FeatureCollection"

    if is_exception:
        preview = text[:500]
        logger.warning(
            "cad_lookup service exception url=%s status=%s content_type=%s preview=%s",
            url,
            status,
            content_type,
            preview,
        )
        return

    if is_feature_collection and settings.DEBUG:
        logger.debug(
            "cad_lookup ok url=%s status=%s content_type=%s preview=%s",
            url,
            status,
            content_type,
            "FeatureCollection received",
        )


def _normalize_value(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _flatten_props(props: dict) -> dict:
    flat = {}
    for key, value in props.items():
        if isinstance(value, dict):
            for subkey, subval in value.items():
                flat[f"{key}.{subkey}"] = subval
                if subkey not in flat:
                    flat[subkey] = subval
        else:
            flat[key] = value
    return flat


def _pick_value(flat_props: dict, keys: list[str]):
    lower_map = {str(k).lower(): v for k, v in flat_props.items()}
    for key in keys:
        val = lower_map.get(key.lower())
        val = _normalize_value(val)
        if val:
            return val
    return None


def _extract_parcel_fields_from_props(props: dict) -> dict:
    flat = _flatten_props(props)
    result = {
        "parcel_number": _pick_value(
            flat,
            [
                "parcel_number",
                "parcelnumber",
                "parcel",
                "label",
                "nationalcadastralreference",
                "national_cadastral_reference",
                "localid",
                "inspireid.localid",
            ],
        ),
        "cadastral_area_code": _pick_value(
            flat,
            [
                "cadastralareacode",
                "katastruzemikod",
                "cadastrecode",
                "cadastralarea",
            ],
        ),
        "cadastral_area_name": _pick_value(
            flat,
            [
                "cadastralareaname",
                "katastruzeminazev",
                "cadastre",
            ],
        ),
        "municipality_code": _pick_value(
            flat,
            [
                "municipalitycode",
                "obeckod",
                "municipality",
            ],
        ),
        "municipality_name": _pick_value(
            flat,
            [
                "municipalityname",
                "obecnazev",
            ],
        ),
        "lv_number": _pick_value(
            flat,
            [
                "lv",
                "lvnumber",
                "listvlastnictvi",
                "landregisternumber",
            ],
        ),
    }
    return {key: value for key, value in result.items() if value}


def _parse_wfs_payload(payload: bytes) -> tuple[dict, bool]:
    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(payload)
    except Exception:
        return {}, False

    features = []
    for elem in root.iter():
        if elem.tag.split("}")[-1].lower() == "cadastralparcel":
            features.append(elem)
    if not features:
        return {}, False

    feature = features[0]
    local_id = None
    namespace = None
    national_ref = None

    for elem in feature.iter():
        tag = elem.tag.split("}")[-1]
        text = elem.text.strip() if elem.text else ""
        if not text:
            continue
        tag_lower = tag.lower()
        if tag_lower == "localid" and local_id is None:
            local_id = text
        elif tag_lower == "namespace" and namespace is None:
            namespace = text
        if "nationalcadastralreference" in tag_lower and national_ref is None:
            national_ref = text

    parcel_number = national_ref or local_id
    fields = {
        "parcel_number": parcel_number,
        "inspire_local_id": local_id,
        "inspire_namespace": namespace,
        "national_cadastral_reference": national_ref,
    }
    return {key: value for key, value in fields.items() if value}, True


def _wgs84_to_sjtsk(lon: float, lat: float) -> tuple[float, float]:
    a_wgs = 6378137.0
    f_wgs = 1 / 298.257223563
    e2_wgs = 2 * f_wgs - f_wgs * f_wgs

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    sin_lon = math.sin(lon_rad)
    cos_lon = math.cos(lon_rad)

    n_wgs = a_wgs / math.sqrt(1 - e2_wgs * sin_lat * sin_lat)
    x = n_wgs * cos_lat * cos_lon
    y = n_wgs * cos_lat * sin_lon
    z = n_wgs * (1 - e2_wgs) * sin_lat

    dx, dy, dz = 589.0, 76.0, 480.0
    x -= dx
    y -= dy
    z -= dz

    a = 6377397.155
    f = 1 / 299.1528128
    e2 = 2 * f - f * f

    p = math.sqrt(x * x + y * y)
    lat_b = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        sin_lat_b = math.sin(lat_b)
        n_b = a / math.sqrt(1 - e2 * sin_lat_b * sin_lat_b)
        lat_b = math.atan2(z + e2 * n_b * sin_lat_b, p)
    lon_b = math.atan2(y, x)

    phi0 = 0.863937979737193
    lam0 = 0.4334234309119251
    k0 = 0.9999
    es = 0.006674372230614
    e = math.sqrt(es)
    s0 = 1.37008346281555
    uq = 1.04216856380474

    alpha = math.sqrt(1.0 + (es * math.cos(phi0) ** 4) / (1.0 - es))
    u0 = math.asin(math.sin(phi0) / alpha)
    g = ((1 + e * math.sin(phi0)) / (1 - e * math.sin(phi0))) ** (alpha * e / 2.0)
    k = (
        math.tan(u0 / 2.0 + math.pi / 4.0)
        / (math.tan(phi0 / 2.0 + math.pi / 4.0) ** alpha)
        * g
    )
    n0 = math.sqrt(1 - es) / (1 - es * math.sin(phi0) ** 2)
    n = math.sin(s0)
    rho0 = k0 * n0 / math.tan(s0)
    ad = math.pi / 2.0 - uq

    gfi = ((1 + e * math.sin(lat_b)) / (1 - e * math.sin(lat_b))) ** (alpha * e / 2.0)
    u = 2.0 * (
        math.atan(k * (math.tan(lat_b / 2.0 + math.pi / 4.0) ** alpha) / gfi)
        - math.pi / 4.0
    )
    deltav = -(lon_b - lam0) * alpha
    s = math.asin(math.cos(ad) * math.sin(u) + math.sin(ad) * math.cos(u) * math.cos(deltav))
    cos_s = math.cos(s)
    if abs(cos_s) < 1e-12:
        return 0.0, 0.0
    d = math.asin(math.cos(u) * math.sin(deltav) / cos_s)
    eps = n * d
    rho = rho0 * (math.tan(s0 / 2.0 + math.pi / 4.0) ** n) / (
        math.tan(s / 2.0 + math.pi / 4.0) ** n
    )
    xk = rho * math.cos(eps)
    yk = rho * math.sin(eps)

    xk, yk = yk, xk
    xk = -xk
    yk = -yk

    xk *= a
    yk *= a
    return xk, yk


def _cad_lookup_by_point(lon: float, lat: float) -> dict:
    x, y = _wgs84_to_sjtsk(lon, lat)
    point = (
        "<gml:Point xmlns:gml='http://www.opengis.net/gml/3.2' "
        "srsName='urn:ogc:def:crs:EPSG::5514'>"
        f"<gml:pos>{x} {y}</gml:pos>"
        "</gml:Point>"
    )
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "storedquery_id": "GetFeatureByPoint",
        "FEATURE_TYPE": CUZK_CP_WFS_TYPENAME,
        "DISTANCE": "0",
        "POINT": point,
    }
    url = f"{CUZK_CP_WFS_ENDPOINT}?{urlencode(params)}"
    _debug_log("cad_lookup request", url=url, mode="point", lon=lon, lat=lat)
    status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    _debug_log(
        "cad_lookup response",
        url=url,
        mode="point",
        status=status,
        content_type=content_type,
        size=len(payload),
    )
    _log_cad_response(url, status, content_type, payload)
    fields, found = _parse_wfs_payload(payload)
    if found:
        fields["cad_lookup_status"] = "ok"
        return fields
    return {"cad_lookup_status": "not_found"}


@lru_cache(maxsize=2048)
def _cached_cad_lookup(lon_round: float, lat_round: float) -> dict:
    lon = float(lon_round)
    lat = float(lat_round)
    delta = 0.000001
    bbox = (lon - delta, lat - delta, lon + delta, lat + delta)

    url = _build_wfs_url(bbox, "2.0.0")
    _debug_log("cad_lookup request", url=url, version="2.0.0", bbox=bbox)
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
        _debug_log(
            "cad_lookup response",
            url=url,
            version="2.0.0",
            status=status,
            content_type=content_type,
            size=len(payload),
        )
        _log_cad_response(url, status, content_type, payload)
        fields, found = _parse_wfs_payload(payload)
        if found:
            fields["cad_lookup_status"] = "ok"
            return fields
    except Exception as err:
        _debug_log("cad_lookup wfs 2.0.0 failed", error=str(err))

    url = _build_wfs_url(bbox, "1.1.0")
    _debug_log("cad_lookup request", url=url, version="1.1.0", bbox=bbox)
    status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    _debug_log(
        "cad_lookup response",
        url=url,
        version="1.1.0",
        status=status,
        content_type=content_type,
        size=len(payload),
    )
    _log_cad_response(url, status, content_type, payload)
    fields, found = _parse_wfs_payload(payload)
    if found:
        fields["cad_lookup_status"] = "ok"
        return fields

    return {"cad_lookup_status": "not_found"}


def _assign_cadastre_attributes(tree: "WorkRecord") -> None:
    if tree.parcel_number:
        return
    lonlat = get_workrecord_lonlat(tree)
    if not lonlat:
        _debug_log("cad_lookup skipped (missing coords)", tree_id=tree.pk)
        return
    lon, lat = lonlat
    try:
        result = _cad_lookup_by_point(lon, lat)
    except Exception as err:
        _debug_log("cad_lookup error", tree_id=tree.pk, error=str(err))
        tree.cad_lookup_status = "error"
        tree.cad_lookup_at = timezone.now()
        tree.save(update_fields=["cad_lookup_status", "cad_lookup_at"])
        return

    update_fields = []
    for key in (
        "parcel_number",
        "cadastral_area_code",
        "cadastral_area_name",
        "municipality_code",
        "municipality_name",
        "lv_number",
        "cad_lookup_status",
    ):
        value = result.get(key)
        if value:
            setattr(tree, key, value)
            update_fields.append(key)
    if tree.parcel_number and not tree.cadastral_area_code and "-" in tree.parcel_number:
        prefix = tree.parcel_number.split("-", 1)[0]
        if prefix.isdigit():
            tree.cadastral_area_code = prefix
            update_fields.append("cadastral_area_code")
    if result.get("cad_lookup_status"):
        tree.cad_lookup_status = result["cad_lookup_status"]
        update_fields.append("cad_lookup_status")
    tree.cad_lookup_at = timezone.now()
    update_fields.append("cad_lookup_at")

    # MVP without GeoDjango; later we can replace this with local parcel polygons + spatial joins.
    tree.save(update_fields=list(dict.fromkeys(update_fields)))


def _add_tree_to_system_dataset(tree: "WorkRecord") -> None:
    from .datasets import get_system_dataset

    dataset = get_system_dataset()
    DatasetTree.objects.get_or_create(dataset=dataset, tree=tree)


@receiver(post_save, sender=WorkRecord)
def _ensure_tree_in_system_dataset(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        _add_tree_to_system_dataset(instance)
    except Exception:
        # Prevent dataset linkage failures from blocking tree creation.
        pass


@receiver(post_save, sender=WorkRecord)
def _assign_cadastre_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        _assign_cadastre_attributes(instance)
    except Exception:
        # Do not block creation if cadastral lookup fails.
        pass
