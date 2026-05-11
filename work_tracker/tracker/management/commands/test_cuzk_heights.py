import json
import time

import requests
from django.core.management.base import BaseCommand, CommandError

from tracker.models import WorkRecord
from tracker.services.cuzk import (
    CuzkHeightError,
    DMP1G_IMAGE_SERVER,
    DMR5G_IMAGE_SERVER,
    estimate_tree_height_from_cuzk,
    wgs84_to_sjtsk,
)


DMP_OK_IMAGE_SERVER = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmp_obrazova_korelace/ImageServer"
DIAGNOSTIC_PIXEL_SIZES = [None, "0.5,0.5", "1,1", "2,2"]


class Command(BaseCommand):
    help = "Test CUZK DMP/DMR height estimate for explicitly selected WorkRecord IDs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            default="",
            help="Comma-separated WorkRecord IDs, for example: 11,25,48",
        )
        parser.add_argument(
            "--codes",
            default="",
            help="Comma-separated UI WorkRecord codes, for example: T1,T2,T15",
        )
        parser.add_argument(
            "--diagnostic",
            action="store_true",
            help="Run detailed ImageServer identify diagnostics for selected records.",
        )

    def handle(self, *args, **options):
        ids = self._parse_ids(options["ids"]) if options["ids"] else []
        codes = self._parse_codes(options["codes"]) if options["codes"] else []
        if not ids and not codes:
            raise CommandError("Use --ids, --codes, or both.")

        records = WorkRecord.objects.all().select_related("project")
        records_by_id = {record.id: record for record in records}
        records_by_code = self._build_code_index(records_by_id.values())
        diagnostic = options["diagnostic"]

        requested_records = []

        if not diagnostic:
            header = (
                "id\trequested_code\tdisplay_label/preferred_id_label/title\tlat\tlon\tdmr_m\tdmp_m\t"
                "estimated_height_m\tduration_ms\terror"
            )
            self.stdout.write(header)

        for record_id in ids:
            record = records_by_id.get(record_id)
            if not record:
                self._write_row(record_id, error="WorkRecord not found")
                continue
            requested_records.append(("", record))

        for code in codes:
            matches = records_by_code.get(self._normalize_code(code), [])
            if not matches:
                self._write_row("", requested_code=code, error="WorkRecord code not found")
                continue
            if len(matches) > 1:
                matched_ids = ", ".join(str(record.id) for record in matches)
                self._write_row(
                    "",
                    requested_code=code,
                    error=f"Ambiguous WorkRecord code; matches IDs: {matched_ids}",
                )
                continue
            requested_records.append((code, matches[0]))

        for requested_code, record in requested_records:
            if diagnostic:
                self._diagnose_and_write(record, requested_code=requested_code)
            else:
                self._estimate_and_write(record, requested_code=requested_code)

    def _estimate_and_write(self, record: WorkRecord, requested_code: str):
        label = self._record_label(record)
        if record.latitude is None or record.longitude is None:
            self._write_row(
                record.id,
                requested_code=requested_code,
                label=label,
                lat=record.latitude,
                lon=record.longitude,
                error="Missing coordinates",
            )
            return

        try:
            lat = float(record.latitude)
            lon = float(record.longitude)
        except (TypeError, ValueError):
            self._write_row(
                record.id,
                requested_code=requested_code,
                label=label,
                lat=record.latitude,
                lon=record.longitude,
                error="Invalid coordinates",
            )
            return

        try:
            result = estimate_tree_height_from_cuzk(lat=lat, lon=lon)
        except CuzkHeightError as exc:
            self._write_row(
                record.id,
                requested_code=requested_code,
                label=label,
                lat=lat,
                lon=lon,
                error=str(exc),
            )
            return
        except Exception as exc:
            self._write_row(
                record.id,
                requested_code=requested_code,
                label=label,
                lat=lat,
                lon=lon,
                error=f"Unexpected error: {exc}",
            )
            return

        warnings = "; ".join(result.get("warnings") or [])
        self._write_row(
            record.id,
            requested_code=requested_code,
            label=label,
            lat=lat,
            lon=lon,
            dmr_m=result["dmr_m"],
            dmp_m=result["dmp_m"],
            estimated_height_m=result["estimated_height_m"],
            duration_ms=result["duration_ms"],
            error=warnings,
        )

    def _parse_ids(self, raw_ids: str) -> list[int]:
        ids = []
        for raw_id in raw_ids.split(","):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            try:
                ids.append(int(raw_id))
            except ValueError as exc:
                raise CommandError(f"Invalid WorkRecord ID: {raw_id}") from exc
        if not ids:
            raise CommandError("--ids must contain at least one WorkRecord ID")
        return ids

    def _parse_codes(self, raw_codes: str) -> list[str]:
        codes = [code.strip() for code in raw_codes.split(",") if code.strip()]
        if not codes:
            raise CommandError("--codes must contain at least one WorkRecord code")
        return codes

    def _build_code_index(self, records) -> dict[str, list[WorkRecord]]:
        index: dict[str, list[WorkRecord]] = {}
        for record in records:
            for code in self._candidate_codes(record):
                normalized = self._normalize_code(code)
                if not normalized:
                    continue
                bucket = index.setdefault(normalized, [])
                if record not in bucket:
                    bucket.append(record)
        return index

    def _candidate_codes(self, record: WorkRecord) -> list[str]:
        values = [
            record.display_label,
            record.map_label,
            record.preferred_id_label,
            record.external_tree_id,
            record.passport_code,
            record.title,
            record.generate_internal_code(),
        ]
        passport_no = record.passport_no or record._passport_number_from_code()
        if passport_no:
            values.extend(
                [
                    f"{record._map_prefix()}{passport_no}",
                    record._format_passport_code(passport_no),
                ]
            )
        return [value for value in values if value]

    def _normalize_code(self, code: str) -> str:
        return str(code).strip().upper()

    def _record_label(self, record: WorkRecord) -> str:
        values = [
            record.display_label,
            record.preferred_id_label,
            record.title,
        ]
        unique = []
        for value in values:
            value = str(value).strip() if value else ""
            if value and value not in unique:
                unique.append(value)
        return " / ".join(unique)

    def _write_row(
        self,
        record_id,
        requested_code="",
        label="",
        lat="",
        lon="",
        dmr_m="",
        dmp_m="",
        estimated_height_m="",
        duration_ms="",
        error="",
    ):
        values = [
            record_id,
            requested_code,
            label,
            lat,
            lon,
            dmr_m,
            dmp_m,
            estimated_height_m,
            duration_ms,
            error,
        ]
        self.stdout.write("\t".join("" if value is None else str(value) for value in values))

    def _diagnose_and_write(self, record: WorkRecord, requested_code: str):
        label = self._record_label(record)
        self.stdout.write("")
        self.stdout.write(
            f"Record id={record.id} requested_code={requested_code or ''} "
            f"label={label} lat={record.latitude} lon={record.longitude}"
        )

        if record.latitude is None or record.longitude is None:
            self.stdout.write("ERROR: Missing coordinates")
            return

        try:
            lat = float(record.latitude)
            lon = float(record.longitude)
        except (TypeError, ValueError):
            self.stdout.write("ERROR: Invalid coordinates")
            return

        try:
            sjtsk_x, sjtsk_y = wgs84_to_sjtsk(lon, lat)
        except Exception as exc:
            self.stdout.write(f"ERROR: Coordinate transform failed: {exc}")
            return

        self.stdout.write(f"S-JTSK EPSG:5514 x={sjtsk_x} y={sjtsk_y}")

        dmr_result = self._identify_diagnostic(
            service_name="DMR 5G",
            image_server_url=DMR5G_IMAGE_SERVER,
            sjtsk_x=sjtsk_x,
            sjtsk_y=sjtsk_y,
            pixel_size=None,
        )
        dmr_value = dmr_result["parsed_value"]
        self._write_diagnostic_result(dmr_result, dmr_value=None)

        for service_name, image_server_url in (
            ("DMP 1G", DMP1G_IMAGE_SERVER),
            ("DMP OK", DMP_OK_IMAGE_SERVER),
        ):
            for pixel_size in DIAGNOSTIC_PIXEL_SIZES:
                result = self._identify_diagnostic(
                    service_name=service_name,
                    image_server_url=image_server_url,
                    sjtsk_x=sjtsk_x,
                    sjtsk_y=sjtsk_y,
                    pixel_size=pixel_size,
                )
                self._write_diagnostic_result(result, dmr_value=dmr_value)

    def _identify_diagnostic(
        self,
        service_name: str,
        image_server_url: str,
        sjtsk_x: float,
        sjtsk_y: float,
        pixel_size: str | None,
    ) -> dict:
        identify_url = f"{image_server_url.rstrip('/')}/identify"
        geometry = {
            "x": sjtsk_x,
            "y": sjtsk_y,
            "spatialReference": {"wkid": 5514},
        }
        params = {
            "f": "json",
            "geometry": json.dumps(geometry, separators=(",", ":")),
            "geometryType": "esriGeometryPoint",
            "returnGeometry": "false",
            "returnCatalogItems": "false",
            "returnAllPixelValues": "true",
        }
        if pixel_size:
            params["pixelSize"] = pixel_size

        start = time.perf_counter()
        try:
            response = requests.get(identify_url, params=params, timeout=5)
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            response.raise_for_status()
            payload = response.json()
            candidates = self._extract_value_candidates(payload)
            parsed_value = self._parse_candidate_value(candidates)
            relevant_payload = self._relevant_payload(payload)
            error = ""
        except requests.Timeout:
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            payload = None
            candidates = []
            parsed_value = None
            relevant_payload = {}
            error = "timeout"
        except Exception as exc:
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            payload = None
            candidates = []
            parsed_value = None
            relevant_payload = {}
            error = str(exc)

        return {
            "service_name": service_name,
            "pixel_size": pixel_size or "none",
            "duration_ms": duration_ms,
            "parsed_value": parsed_value,
            "value_field": candidates[0]["path"] if candidates else "",
            "candidates": candidates,
            "relevant_payload": relevant_payload,
            "error": error,
        }

    def _write_diagnostic_result(self, result: dict, dmr_value: float | None):
        parsed_value = result["parsed_value"]
        diff = ""
        if dmr_value is not None and parsed_value is not None:
            diff = round(parsed_value - dmr_value, 3)
        self.stdout.write(
            "service={service} pixelSize={pixel_size} parsed_value={parsed_value} "
            "value_field={field} dmp_minus_dmr={diff} duration_ms={duration_ms} error={error}".format(
                service=result["service_name"],
                pixel_size=result["pixel_size"],
                parsed_value="" if parsed_value is None else round(parsed_value, 3),
                field=result["value_field"] or "",
                diff=diff,
                duration_ms=result["duration_ms"],
                error=result["error"],
            )
        )
        self.stdout.write(f"  candidates={json.dumps(result['candidates'], ensure_ascii=False)}")
        self.stdout.write(
            "  raw_relevant="
            + json.dumps(result["relevant_payload"], ensure_ascii=False, sort_keys=True)
        )

    def _extract_value_candidates(self, payload) -> list[dict]:
        candidates = []

        def visit(value, path):
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    if self._is_value_candidate_key(key):
                        candidates.append({"path": child_path, "value": child})
                    visit(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}[{index}]")

        visit(payload, "")
        return candidates

    def _is_value_candidate_key(self, key: str) -> bool:
        key = str(key).lower()
        return key in {"value", "values", "pixelvalue", "pixelvalues"} or "pixelvalue" in key

    def _parse_candidate_value(self, candidates: list[dict]) -> float | None:
        for candidate in candidates:
            parsed = self._coerce_float(candidate["value"])
            if parsed is not None:
                return parsed
        return None

    def _coerce_float(self, value) -> float | None:
        if isinstance(value, list):
            for item in value:
                parsed = self._coerce_float(item)
                if parsed is not None:
                    return parsed
            return None
        if isinstance(value, dict):
            for key in ("value", "pixelValue"):
                if key in value:
                    parsed = self._coerce_float(value[key])
                    if parsed is not None:
                        return parsed
            return None
        if value in (None, "", "NoData", "NaN"):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed

    def _relevant_payload(self, payload) -> dict:
        if not isinstance(payload, dict):
            return {}
        keys = [
            "objectId",
            "name",
            "value",
            "values",
            "location",
            "properties",
            "catalogItems",
            "catalogItemVisibilities",
            "error",
        ]
        return {key: payload.get(key) for key in keys if key in payload}
