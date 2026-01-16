import csv
import shutil
import time
import zipfile
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import (
    RuianCadastralArea,
    RuianCadastralAreaMunicipality,
    RuianImportMeta,
    RuianMunicipality,
)


DEFAULT_OBEC_URL = "https://services.cuzk.gov.cz/sestavy/cis/UI_OBEC.zip"
DEFAULT_KU_URL = "https://services.cuzk.gov.cz/sestavy/cis/UI_KATASTRALNI_UZEMI.zip"
DEFAULT_ZSJ_URL = "https://services.cuzk.gov.cz/sestavy/cis/UI_ZSJ.zip"  # optional / future use


def _normalize_key(key: str) -> str:
    if key is None:
        return ""
    return key.strip().lower().replace("-", "_")


def _get_value(row: dict, keys: list[str]) -> str | None:
    lowered = {}
    for raw_key, raw_value in row.items():
        norm_key = _normalize_key(raw_key)
        if not norm_key:
            continue
        lowered[norm_key] = raw_value
    for key in keys:
        value = lowered.get(_normalize_key(key))
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return None


def _find_csv(root: Path, candidates: list[str]) -> Path | None:
    names = {c.lower() for c in candidates}
    for path in root.rglob("*.csv"):
        if path.name.lower() in names:
            return path
    return None


def _open_csv_with_fallback(path: Path) -> tuple[TextIO, str]:
    encodings = ["utf-8-sig", "cp1250", "iso-8859-2"]
    last_err = None
    for encoding in encodings:
        try:
            handle = path.open("r", encoding=encoding, newline="")
            handle.read(4096)
            handle.seek(0)
            return handle, encoding
        except UnicodeDecodeError as err:
            last_err = err
    if last_err:
        raise last_err
    raise UnicodeDecodeError("unknown", b"", 0, 1, "failed to open file")


def _download_zip(url: str, dest_path: Path) -> None:
    delays = [1, 2, 4]
    last_err = None
    for attempt, delay in enumerate(delays, start=1):
        try:
            req = Request(url, headers={"User-Agent": "work_tracker/1.0"})
            with urlopen(req, timeout=60) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type.lower():
                    raise ValueError("download returned HTML, wrong URL")
                data = resp.read()
            dest_path.write_bytes(data)
            if not zipfile.is_zipfile(dest_path):
                raise ValueError("downloaded file is not a ZIP archive")
            return
        except HTTPError as err:
            last_err = err
            if err.code != 500 or attempt == len(delays):
                raise
        except (URLError, ValueError) as err:
            last_err = err
            if attempt == len(delays):
                raise
        time.sleep(delay)
    if last_err:
        raise last_err


class Command(BaseCommand):
    help = "Import RUIAN lookup tables (cadastral areas, municipalities, mapping)."

    def add_arguments(self, parser):
        parser.add_argument("--obec-url", default=DEFAULT_OBEC_URL)
        parser.add_argument("--ku-url", default=DEFAULT_KU_URL)
        parser.add_argument("--source-dir", default="")
        parser.add_argument("--cache-dir", default="")
        parser.add_argument("--force-download", action="store_true")

    def handle(self, *args, **options):
        cache_dir = options["cache_dir"] or str(settings.BASE_DIR / "var" / "ruian")
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        source_dir = Path(options["source_dir"]) if options["source_dir"] else None
        obec_url = options["obec_url"]
        ku_url = options["ku_url"]

        if source_dir:
            extracted_dir = source_dir
            source_zip_name = f"dir:{source_dir.name}"
        else:
            extracted_dir = cache_dir / "extracted"
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
            extracted_dir.mkdir(parents=True, exist_ok=True)

            parsed_obec = urlparse(obec_url)
            parsed_ku = urlparse(ku_url)
            obec_zip_name = Path(parsed_obec.path).name or "UI_OBEC.zip"
            ku_zip_name = Path(parsed_ku.path).name or "UI_KATASTRALNI_UZEMI.zip"
            obec_zip_path = cache_dir / obec_zip_name
            ku_zip_path = cache_dir / ku_zip_name

            if options["force_download"] or not obec_zip_path.exists():
                self.stdout.write(f"Downloading {obec_url} ...")
                _download_zip(obec_url, obec_zip_path)
            if options["force_download"] or not ku_zip_path.exists():
                self.stdout.write(f"Downloading {ku_url} ...")
                _download_zip(ku_url, ku_zip_path)
            if not obec_zip_path.exists() or not ku_zip_path.exists():
                raise FileNotFoundError("Missing source ZIPs")

            obec_extract_dir = extracted_dir / "obec"
            ku_extract_dir = extracted_dir / "ku"
            for target in (obec_extract_dir, ku_extract_dir):
                if target.exists():
                    shutil.rmtree(target)
                target.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(obec_zip_path, "r") as zf:
                zf.extractall(obec_extract_dir)
            with zipfile.ZipFile(ku_zip_path, "r") as zf:
                zf.extractall(ku_extract_dir)
            source_zip_name = f"{obec_zip_name};{ku_zip_name}"

        obce_csv = _find_csv(extracted_dir, ["ui_obec.csv", "obce.csv"])
        ku_csv = _find_csv(
            extracted_dir,
            ["ui_katastralni_uzemi.csv", "katastralni_uzemi.csv"],
        )
        if not obce_csv or not ku_csv:
            raise FileNotFoundError(
                "Expected UI_OBEC/UI_KATASTRALNI_UZEMI CSVs (or legacy obce/katastralni_uzemi) in source"
            )

        municipalities: dict[str, str] = {}
        csvfile, encoding = _open_csv_with_fallback(obce_csv)
        self.stdout.write(f"Reading {obce_csv.name} with {encoding}")
        with csvfile:
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                if not row or not any(str(val).strip() for val in row.values() if val is not None):
                    continue
                code = _get_value(row, ["KOD"])
                name = _get_value(row, ["NAZEV"])
                if code and name:
                    municipalities[code] = name

        cadastral_areas: dict[str, str] = {}
        mapping_pairs: list[tuple[str, str]] = []
        csvfile, encoding = _open_csv_with_fallback(ku_csv)
        self.stdout.write(f"Reading {ku_csv.name} with {encoding}")
        with csvfile:
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                if not row or not any(str(val).strip() for val in row.values() if val is not None):
                    continue
                code = _get_value(row, ["KOD"])
                name = _get_value(row, ["NAZEV"])
                municipality_code = _get_value(row, ["OBEC_KOD", "KOD_OBEC", "KOD_OBCE"])
                if code and name:
                    cadastral_areas[code] = name
                if code and municipality_code:
                    mapping_pairs.append((code, municipality_code))

        with transaction.atomic():
            RuianCadastralAreaMunicipality.objects.all().delete()
            RuianCadastralArea.objects.all().delete()
            RuianMunicipality.objects.all().delete()

            RuianMunicipality.objects.bulk_create(
                [RuianMunicipality(code=code, name=name) for code, name in municipalities.items()],
                batch_size=1000,
            )
            RuianCadastralArea.objects.bulk_create(
                [RuianCadastralArea(code=code, name=name) for code, name in cadastral_areas.items()],
                batch_size=1000,
            )
            RuianCadastralAreaMunicipality.objects.bulk_create(
                [
                    RuianCadastralAreaMunicipality(
                        cadastral_area_id=ku_code, municipality_id=obec_code
                    )
                    for ku_code, obec_code in mapping_pairs
                    if ku_code in cadastral_areas and obec_code in municipalities
                ],
                batch_size=1000,
            )

            RuianImportMeta.objects.create(
                source_url=f"{obec_url};{ku_url}" if not source_dir else "",
                source_zip_name=source_zip_name,
            )

        self.stdout.write(
            f"Imported {len(cadastral_areas)} cadastral areas, "
            f"{len(municipalities)} municipalities, "
            f"{len(mapping_pairs)} mappings"
        )
