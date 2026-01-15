import json
import logging
import re
import string
import unicodedata
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
CUZK_CP_WFS_TYPENAME = "CP:CadastralParcel"
RUIAN_REST_BASE = (
    "https://ags.cuzk.gov.cz/arcgis/rest/services/"
    "RUIAN/Prohlizeci_sluzba_nad_daty_RUIAN/MapServer"
)
_RUIAN_LAYER_INFO_LOGGED = False
_RUIAN_LAYER_ID_CACHE = None
_RUIAN_LAYER_NAME_CACHE = None
_RUIAN_FIELDS_CACHE = {}
_RUIAN_OBEC_FIELDS_CACHE = {}
_RUIAN_OBEC_FIELDS_PRINTED = False
RUIAN_OBEC_LAYER_ID = 12


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
    params = {
        "SERVICE": "WFS",
        "REQUEST": "GetFeature",
        "VERSION": version,
        "TYPENAMES": CUZK_CP_WFS_TYPENAME,
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
    }
    if version == "2.0.0":
        params["COUNT"] = 1
    else:
        params["MAXFEATURES"] = 1
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

    feature = None
    for elem in root.iter():
        if elem.tag.split("}")[-1].lower() == "cadastralparcel":
            feature = elem
            break
    if feature is None:
        return {}, False

    local_id = None
    namespace = None
    national_ref = None
    tags_of_interest = []

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
        if "cadastral" in tag_lower or "reference" in tag_lower:
            tags_of_interest.append(f"{tag}={text}")

    if settings.DEBUG:
        logger.debug(
            "cad_lookup wfs feature localId=%s namespace=%s nationalRef=%s",
            local_id,
            namespace,
            national_ref,
        )
        logger.debug(
            "cad_lookup wfs tags %s",
            json.dumps(tags_of_interest, ensure_ascii=True),
        )

    parcel_number = national_ref or local_id
    fields = {
        "parcel_number": parcel_number,
        "inspire_local_id": local_id,
        "inspire_namespace": namespace,
        "national_cadastral_reference": national_ref,
    }
    return {key: value for key, value in fields.items() if value}, True


def _lookup_attr(attributes: dict, field_name: str):
    if not attributes or not field_name:
        return None
    for key, value in attributes.items():
        if key.lower() == field_name.lower():
            return value
    return None


def _normalize_ruian_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    cleaned = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", cleaned)
    return cleaned.lower().strip()


def resolve_ruian_ku_layer() -> int | None:
    global _RUIAN_LAYER_ID_CACHE, _RUIAN_LAYER_NAME_CACHE
    if _RUIAN_LAYER_ID_CACHE is not None:
        return _RUIAN_LAYER_ID_CACHE
    url = f"{RUIAN_REST_BASE}?f=pjson"
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    except Exception as err:
        _debug_log("cad_ku_layer_list failed", error=str(err))
        return None
    if status and status >= 400:
        _debug_log("cad_ku_layer_list http error", status=status)
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as err:
        _debug_log("cad_ku_layer_list json error", error=str(err))
        return None
    layers = data.get("layers") or []
    print("CAD_KU: available layers:")
    for layer in layers[:200]:
        if isinstance(layer, dict) and "id" in layer and "name" in layer:
            print(f"  {layer['id']}: {layer['name']}")
    for layer in layers:
        name = layer.get("name") if isinstance(layer, dict) else None
        layer_id = layer.get("id") if isinstance(layer, dict) else None
        if name is None or layer_id is None:
            continue
        name_norm = _normalize_ruian_name(str(name))
        tokens = set(name_norm.split())
        has_katastr = "katastr" in name_norm
        has_uzemi = "uzemi" in name_norm or "u" in tokens and "zemi" in tokens
        has_ku_token = "ku" in tokens or "k u" in name_norm or "k u" in name_norm
        is_match = (has_katastr and has_uzemi) or has_ku_token
        if is_match:
            _RUIAN_LAYER_ID_CACHE = int(layer_id)
            _RUIAN_LAYER_NAME_CACHE = str(name)
            print("CAD_KU: resolved layer", _RUIAN_LAYER_ID_CACHE, _RUIAN_LAYER_NAME_CACHE)
            if settings.DEBUG:
                _debug_log("cad_ku_layer resolved", name=name, layer_id=layer_id)
            return _RUIAN_LAYER_ID_CACHE
    for layer in layers:
        name = layer.get("name") if isinstance(layer, dict) else None
        layer_id = layer.get("id") if isinstance(layer, dict) else None
        if name is None or layer_id is None:
            continue
        name_norm = _normalize_ruian_name(str(name))
        if "katastr" in name_norm and "parcela" not in name_norm:
            _RUIAN_LAYER_ID_CACHE = int(layer_id)
            _RUIAN_LAYER_NAME_CACHE = str(name)
            print("CAD_KU: resolved layer", _RUIAN_LAYER_ID_CACHE, _RUIAN_LAYER_NAME_CACHE)
            if settings.DEBUG:
                _debug_log("cad_ku_layer resolved", name=name, layer_id=layer_id)
            return _RUIAN_LAYER_ID_CACHE
    return None


def resolve_fields(layer_id: int) -> dict:
    cached = _RUIAN_FIELDS_CACHE.get(layer_id)
    if cached:
        return cached
    url = f"{RUIAN_REST_BASE}/{layer_id}?f=pjson"
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    except Exception as err:
        _debug_log("cad_ku_fields failed", layer_id=layer_id, error=str(err))
        return {}
    if status and status >= 400:
        _debug_log("cad_ku_fields http error", layer_id=layer_id, status=status)
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as err:
        _debug_log("cad_ku_fields json error", layer_id=layer_id, error=str(err))
        return {}
    fields = data.get("fields") or []
    if settings.DEBUG and layer_id == 7:
        global _RUIAN_OBEC_FIELDS_PRINTED
        if not _RUIAN_OBEC_FIELDS_PRINTED:
            obec_candidates = []
            for field in fields:
                name = field.get("name") if isinstance(field, dict) else None
                if name and "obec" in _normalize_ruian_name(str(name)):
                    obec_candidates.append(name)
            print("CAD_KU: obec field candidates (layer 7):", obec_candidates)
            _RUIAN_OBEC_FIELDS_PRINTED = True
    result = {}
    for field in fields:
        name = field.get("name") if isinstance(field, dict) else None
        ftype = field.get("type") if isinstance(field, dict) else None
        if not name:
            continue
        name_norm = _normalize_ruian_name(str(name))
        if not result.get("ku_code"):
            if name_norm == "kod":
                result["ku_code"] = name
            elif "kod" in name_norm and ("ku" in name_norm or "katastr" in name_norm):
                result["ku_code"] = name
            elif "kod" in name_norm and ftype and "integer" in ftype.lower():
                result.setdefault("ku_code", name)
        if not result.get("ku_name"):
            if name_norm == "nazev":
                result["ku_name"] = name
            elif "nazev" in name_norm and ("ku" in name_norm or "katastr" in name_norm):
                result["ku_name"] = name
        if name_norm == "obec":
            if ftype and "integer" in str(ftype).lower():
                if not result.get("municipality_code"):
                    result["municipality_code"] = name
            else:
                if not result.get("municipality_name"):
                    result["municipality_name"] = name
        if not result.get("municipality_name") and "obec" in name_norm and "nazev" in name_norm:
            result["municipality_name"] = name
        if not result.get("municipality_code") and "obec" in name_norm and "kod" in name_norm:
            result["municipality_code"] = name
    _RUIAN_FIELDS_CACHE[layer_id] = result
    if settings.DEBUG:
        _debug_log(
            "cad_ku_fields resolved",
            layer_id=layer_id,
            fields=result,
        )
    return result


def resolve_obec_fields(layer_id: int) -> dict:
    cached = _RUIAN_OBEC_FIELDS_CACHE.get(layer_id)
    if cached:
        return cached
    url = f"{RUIAN_REST_BASE}/{layer_id}?f=pjson"
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    except Exception as err:
        _debug_log("cad_obec_fields failed", layer_id=layer_id, error=str(err))
        return {}
    if status and status >= 400:
        _debug_log("cad_obec_fields http error", layer_id=layer_id, status=status)
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as err:
        _debug_log("cad_obec_fields json error", layer_id=layer_id, error=str(err))
        return {}
    fields = data.get("fields") or []
    result = {}
    for field in fields:
        name = field.get("name") if isinstance(field, dict) else None
        if not name:
            continue
        name_norm = _normalize_ruian_name(str(name))
        if not result.get("municipality_name") and "nazev" in name_norm:
            result["municipality_name"] = name
        if not result.get("municipality_code") and "kod" in name_norm:
            result["municipality_code"] = name
    _RUIAN_OBEC_FIELDS_CACHE[layer_id] = result
    return result


@lru_cache(maxsize=2048)
def fetch_municipality_by_name(name: str) -> dict:
    if not name:
        return {}
    fields = resolve_obec_fields(RUIAN_OBEC_LAYER_ID)
    if not fields.get("municipality_name"):
        return {}
    safe_name = name.replace("'", "''")
    where_value = f"'{safe_name}'"
    params = {
        "where": f"{fields['municipality_name']}={where_value}",
        "outFields": ",".join(
            value
            for value in (
                fields.get("municipality_name"),
                fields.get("municipality_code"),
            )
            if value
        ),
        "returnGeometry": "false",
        "f": "pjson",
    }
    url = f"{RUIAN_REST_BASE}/{RUIAN_OBEC_LAYER_ID}/query?{urlencode(params)}"
    _debug_log("cad_obec_lookup request", url=url)
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    except Exception as err:
        _debug_log("cad_obec_lookup error", error=str(err))
        return {}
    if status and status >= 400:
        _debug_log("cad_obec_lookup http error", status=status)
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as err:
        _debug_log("cad_obec_lookup json error", error=str(err))
        return {}
    features = data.get("features") or []
    if not features:
        return {}
    attributes = features[0].get("attributes") if isinstance(features[0], dict) else None
    if not attributes:
        return {}
    result = {
        "municipality_name": _lookup_attr(attributes, fields.get("municipality_name")),
        "municipality_code": _lookup_attr(attributes, fields.get("municipality_code")),
    }
    return {key: value for key, value in result.items() if value}


def _log_ruian_layer_info_once() -> None:
    global _RUIAN_LAYER_INFO_LOGGED
    if _RUIAN_LAYER_INFO_LOGGED or not settings.DEBUG:
        return
    url = f"{RUIAN_REST_BASE}/{RUIAN_KU_LAYER_ID}?f=pjson"
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=0)
    except Exception as err:
        _debug_log("cad_ku_layer_info failed", error=str(err))
        _RUIAN_LAYER_INFO_LOGGED = True
        return
    _debug_log(
        "cad_ku_layer_info",
        status=status,
        content_type=content_type,
        preview=payload[:500].decode("utf-8", errors="replace"),
    )
    _RUIAN_LAYER_INFO_LOGGED = True


@lru_cache(maxsize=2048)
def fetch_ku_detail_rest(kod_ku: str) -> dict:
    print("CAD_KU: resolving layer/fields...")
    layer_id = resolve_ruian_ku_layer()
    print("CAD_KU: layer_id=", layer_id, "layer_name=", _RUIAN_LAYER_NAME_CACHE)
    if layer_id is None:
        _log_ruian_layer_info_once()
        return {}
    fields = resolve_fields(layer_id)
    print("CAD_KU: fields=", fields)
    if not fields.get("ku_code") or not fields.get("ku_name"):
        _log_ruian_layer_info_once()
        return {}
    where_value = int(kod_ku) if re.match(r"^\d+$", str(kod_ku)) else f"'{kod_ku}'"
    out_fields = [
        fields.get("ku_name"),
        fields.get("municipality_name"),
        fields.get("municipality_code"),
    ]
    deduped_fields = []
    seen = set()
    for field in out_fields:
        if not field or field in seen:
            continue
        seen.add(field)
        deduped_fields.append(field)
    params = {
        "where": f"{fields['ku_code']}={where_value}",
        "outFields": ",".join(deduped_fields),
        "returnGeometry": "false",
        "f": "pjson",
    }
    url = f"{RUIAN_REST_BASE}/{layer_id}/query?{urlencode(params)}"
    print("CAD_KU: query_url=", url)
    _debug_log("cad_ku_lookup request", url=url)
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
    except Exception as err:
        _debug_log("cad_ku_lookup error", kod=kod_ku, error=str(err))
        _log_ruian_layer_info_once()
        return {}
    preview = payload[:300].decode("utf-8", errors="replace")
    print("CAD_KU: http status=", status, "content_type=", content_type)
    print("CAD_KU: response preview=", preview)
    if status and status >= 400:
        _debug_log("cad_ku_lookup http error", kod=kod_ku, status=status)
        _log_ruian_layer_info_once()
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as err:
        _debug_log("cad_ku_lookup json error", kod=kod_ku, error=str(err))
        _log_ruian_layer_info_once()
        return {}

    if settings.DEBUG and data.get("error"):
        _debug_log("cad_ku_lookup error response", kod=kod_ku, error=data.get("error"))
        print("CAD_KU: error=", data.get("error"))

    features = data.get("features") or []
    print("CAD_KU: features=", len(features))
    if not features:
        if settings.DEBUG:
            _debug_log("cad_ku_lookup empty", layer_id=layer_id, where=params.get("where"))
        return {}
    attributes = features[0].get("attributes") if isinstance(features[0], dict) else None
    if not attributes:
        return {}
    result = {
        "cadastral_area_name": _lookup_attr(attributes, fields.get("ku_name")),
        "municipality_name": _lookup_attr(attributes, fields.get("municipality_name")),
        "municipality_code": _lookup_attr(attributes, fields.get("municipality_code")),
    }
    if not result.get("municipality_name") and result.get("cadastral_area_name"):
        obec_detail = fetch_municipality_by_name(result["cadastral_area_name"])
        if obec_detail.get("municipality_name"):
            result["municipality_name"] = obec_detail.get("municipality_name")
        if obec_detail.get("municipality_code"):
            result["municipality_code"] = obec_detail.get("municipality_code")
    result = {key: value for key, value in result.items() if value}
    if result:
        print(
            "CAD_KU: parsed",
            result.get("cadastral_area_name"),
            result.get("municipality_name"),
            result.get("municipality_code"),
        )
    if result:
        _debug_log(
            "cad_ku_lookup ok",
            kod=kod_ku,
            ku=result.get("cadastral_area_name"),
            obec=result.get("municipality_name"),
        )
    return result


@lru_cache(maxsize=2048)
def _cached_cad_lookup(lon_round: float, lat_round: float) -> dict:
    lon = float(lon_round)
    lat = float(lat_round)
    delta = 0.0002
    bbox = (lon - delta, lat - delta, lon + delta, lat + delta)

    url = _build_wfs_url(bbox, "2.0.0")
    _debug_log("cad_lookup request", url=url)
    try:
        status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
        _log_cad_response(url, status, content_type, payload)
        fields, found = _parse_wfs_payload(payload)
        if found:
            fields["cad_lookup_status"] = "ok"
            return fields
    except Exception as err:
        _debug_log("cad_lookup wfs 2.0.0 failed", error=str(err))

    url = _build_wfs_url(bbox, "1.1.0")
    _debug_log("cad_lookup request", url=url)
    status, content_type, payload = _http_get(url, timeout_s=3, retries=1)
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
        result = _cached_cad_lookup(round(lon, 6), round(lat, 6))
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
    if result.get("cad_lookup_status"):
        tree.cad_lookup_status = result["cad_lookup_status"]
        update_fields.append("cad_lookup_status")
    tree.cad_lookup_at = timezone.now()
    update_fields.append("cad_lookup_at")

    # MVP without GeoDjango; later we can replace this with local parcel polygons + spatial joins.
    tree.save(update_fields=list(dict.fromkeys(update_fields)))

    if tree.parcel_number:
        match = re.match(r"^(\d{6})-", tree.parcel_number)
        ku_code = match.group(1) if match else None
        if ku_code and not tree.cadastral_area_code:
            tree.cadastral_area_code = ku_code
            tree.save(update_fields=["cadastral_area_code"])
        if ku_code and (not tree.cadastral_area_name or not tree.municipality_name):
            print(
                f"CAD_KU: start wr={tree.id} parcel={tree.parcel_number} "
                f"ku_code={tree.cadastral_area_code} status={tree.cad_lookup_status}"
            )
            ku_detail = fetch_ku_detail_rest(ku_code)
            ku_updates = []
            if not tree.cadastral_area_name and ku_detail.get("cadastral_area_name"):
                tree.cadastral_area_name = ku_detail["cadastral_area_name"]
                ku_updates.append("cadastral_area_name")
            if not tree.municipality_name and ku_detail.get("municipality_name"):
                tree.municipality_name = ku_detail["municipality_name"]
                ku_updates.append("municipality_name")
            if not tree.municipality_code and ku_detail.get("municipality_code"):
                tree.municipality_code = ku_detail["municipality_code"]
                ku_updates.append("municipality_code")
            if ku_updates:
                tree.save(update_fields=ku_updates)


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
