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
        parser.add_argument(
            "--samples-diagnostic",
            action="store_true",
            help="Test ImageServer getSamples for a small circular grid around selected records.",
        )
        parser.add_argument(
            "--nearby-diagnostic",
            action="store_true",
            help="Estimate height from DMR center and max DMP OK identify samples around the point.",
        )
        parser.add_argument("--radius-m", type=float, default=4.0)
        parser.add_argument("--step-m", type=float, default=2.0)

    def handle(self, *args, **options):
        ids = self._parse_ids(options["ids"]) if options["ids"] else []
        codes = self._parse_codes(options["codes"]) if options["codes"] else []
        if not ids and not codes:
            raise CommandError("Use --ids, --codes, or both.")

        records = WorkRecord.objects.all().select_related("project")
        records_by_id = {record.id: record for record in records}
        records_by_code = self._build_code_index(records_by_id.values())
        diagnostic = options["diagnostic"]
        samples_diagnostic = options["samples_diagnostic"]
        nearby_diagnostic = options["nearby_diagnostic"]

        requested_records = []

        if not diagnostic and not samples_diagnostic and not nearby_diagnostic:
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
            if nearby_diagnostic:
                self._nearby_diagnose_and_write(
                    record,
                    requested_code=requested_code,
                    radius_m=options["radius_m"],
                )
            elif samples_diagnostic:
                self._samples_diagnose_and_write(
                    record,
                    requested_code=requested_code,
                    radius_m=options["radius_m"],
                    step_m=options["step_m"],
                )
            elif diagnostic:
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

    def _samples_diagnose_and_write(
        self,
        record: WorkRecord,
        requested_code: str,
        radius_m: float,
        step_m: float,
    ):
        label = self._record_label(record)
        self.stdout.write("")
        self.stdout.write(
            f"Samples diagnostic record id={record.id} requested_code={requested_code or ''} "
            f"label={label} lat={record.latitude} lon={record.longitude} radius_m={radius_m} step_m={step_m}"
        )

        if record.latitude is None or record.longitude is None:
            self.stdout.write("ERROR: Missing coordinates")
            return

        try:
            lat = float(record.latitude)
            lon = float(record.longitude)
            sjtsk_x, sjtsk_y = wgs84_to_sjtsk(lon, lat)
        except Exception as exc:
            self.stdout.write(f"ERROR: Coordinate transform failed: {exc}")
            return

        points = self._circle_grid_points(sjtsk_x, sjtsk_y, radius_m=radius_m, step_m=step_m)
        self.stdout.write(f"S-JTSK EPSG:5514 x={sjtsk_x} y={sjtsk_y} points={len(points)}")
        self.stdout.write(f"sample_points_first5={json.dumps(points[:5], ensure_ascii=False)}")

        any_samples_ok = False
        for service_name, image_server_url in (
            ("DMR 5G", DMR5G_IMAGE_SERVER),
            ("DMP OK", DMP_OK_IMAGE_SERVER),
        ):
            result = self._get_samples_diagnostic(service_name, image_server_url, points)
            if result["ok"]:
                any_samples_ok = True
            self._write_samples_result(result)

        if any_samples_ok:
            self.stdout.write(
                "getSamples OK: max_in_radius can use two requests, DMP OK samples and DMR 5G samples."
            )
            return

        self.stdout.write("getSamples did not return usable samples; checking exportImage fallback.")
        for service_name, image_server_url in (
            ("DMR 5G", DMR5G_IMAGE_SERVER),
            ("DMP OK", DMP_OK_IMAGE_SERVER),
        ):
            result = self._export_image_diagnostic(
                service_name,
                image_server_url,
                sjtsk_x=sjtsk_x,
                sjtsk_y=sjtsk_y,
                radius_m=radius_m,
                step_m=step_m,
            )
            self._write_export_image_result(result)

    def _circle_grid_points(self, sjtsk_x: float, sjtsk_y: float, radius_m: float, step_m: float) -> list[list[float]]:
        if radius_m <= 0:
            raise CommandError("--radius-m must be greater than 0")
        if step_m <= 0:
            raise CommandError("--step-m must be greater than 0")

        points = []
        steps = int(radius_m // step_m)
        offsets = [round(i * step_m, 6) for i in range(-steps, steps + 1)]
        for dx in offsets:
            for dy in offsets:
                if dx * dx + dy * dy <= radius_m * radius_m + 1e-9:
                    points.append([sjtsk_x + dx, sjtsk_y + dy])
        return points

    def _get_samples_diagnostic(self, service_name: str, image_server_url: str, points: list[list[float]]) -> dict:
        url = f"{image_server_url.rstrip('/')}/getSamples"
        geometry = {
            "points": points,
            "spatialReference": {"wkid": 5514},
        }
        params = {
            "f": "json",
            "geometry": json.dumps(geometry, separators=(",", ":")),
            "geometryType": "esriGeometryMultipoint",
            "returnGeometry": "false",
        }
        start = time.perf_counter()
        status_code = None
        content_type = ""
        try:
            response = requests.post(url, data=params, timeout=5)
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            status_code = response.status_code
            content_type = response.headers.get("Content-Type", "")
            raw_text = response.text
            try:
                payload = response.json()
            except ValueError:
                payload = None
            values = self._extract_sample_values(payload)
            error = "" if response.ok else f"HTTP {response.status_code}"
        except Exception as exc:
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            raw_text = ""
            payload = None
            values = []
            error = str(exc)

        return {
            "ok": bool(values),
            "service_name": service_name,
            "url": url,
            "method": "POST",
            "status_code": status_code,
            "content_type": content_type,
            "sent_points": len(points),
            "returned_values": len(values),
            "min_value": min(values) if values else None,
            "max_value": max(values) if values else None,
            "duration_ms": duration_ms,
            "raw_sample": self._short_raw(payload if payload is not None else raw_text),
            "error": error,
        }

    def _extract_sample_values(self, payload) -> list[float]:
        if not isinstance(payload, dict):
            return []
        samples = payload.get("samples")
        if not isinstance(samples, list):
            return []
        values = []
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            parsed = self._coerce_float(sample.get("value"))
            if parsed is not None:
                values.append(parsed)
        return values

    def _export_image_diagnostic(
        self,
        service_name: str,
        image_server_url: str,
        sjtsk_x: float,
        sjtsk_y: float,
        radius_m: float,
        step_m: float,
    ) -> dict:
        url = f"{image_server_url.rstrip('/')}/exportImage"
        size_px = max(1, int(round((radius_m * 2) / step_m)) + 1)
        params = {
            "f": "json",
            "bbox": f"{sjtsk_x - radius_m},{sjtsk_y - radius_m},{sjtsk_x + radius_m},{sjtsk_y + radius_m}",
            "bboxSR": "5514",
            "imageSR": "5514",
            "size": f"{size_px},{size_px}",
            "format": "tiff",
            "pixelType": "F32",
            "interpolation": "RSP_NearestNeighbor",
        }
        start = time.perf_counter()
        status_code = None
        content_type = ""
        try:
            response = requests.get(url, params=params, timeout=5)
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            status_code = response.status_code
            content_type = response.headers.get("Content-Type", "")
            raw_text = response.text
            try:
                payload = response.json()
            except ValueError:
                payload = None
            error = "" if response.ok else f"HTTP {response.status_code}"
        except Exception as exc:
            duration_ms = int(round((time.perf_counter() - start) * 1000))
            raw_text = ""
            payload = None
            error = str(exc)

        return {
            "ok": status_code == 200 and isinstance(payload, dict) and bool(payload.get("href")),
            "service_name": service_name,
            "url": url,
            "method": "GET",
            "status_code": status_code,
            "content_type": content_type,
            "href": payload.get("href") if isinstance(payload, dict) else "",
            "width": payload.get("width") if isinstance(payload, dict) else "",
            "height": payload.get("height") if isinstance(payload, dict) else "",
            "duration_ms": duration_ms,
            "raw_sample": self._short_raw(payload if payload is not None else raw_text),
            "error": error,
        }

    def _write_samples_result(self, result: dict):
        self.stdout.write(
            "getSamples service={service} method={method} status={status} content_type={content_type} "
            "sent_points={sent_points} returned_values={returned_values} min={min_value} max={max_value} "
            "duration_ms={duration_ms} error={error}".format(
                service=result["service_name"],
                method=result["method"],
                status=result["status_code"],
                content_type=result["content_type"],
                sent_points=result["sent_points"],
                returned_values=result["returned_values"],
                min_value="" if result["min_value"] is None else round(result["min_value"], 3),
                max_value="" if result["max_value"] is None else round(result["max_value"], 3),
                duration_ms=result["duration_ms"],
                error=result["error"],
            )
        )
        self.stdout.write(f"  endpoint={result['url']}")
        self.stdout.write(f"  raw_sample={result['raw_sample']}")

    def _write_export_image_result(self, result: dict):
        self.stdout.write(
            "exportImage service={service} method={method} status={status} content_type={content_type} "
            "width={width} height={height} duration_ms={duration_ms} error={error}".format(
                service=result["service_name"],
                method=result["method"],
                status=result["status_code"],
                content_type=result["content_type"],
                width=result["width"],
                height=result["height"],
                duration_ms=result["duration_ms"],
                error=result["error"],
            )
        )
        self.stdout.write(f"  href={result['href']}")
        self.stdout.write(f"  raw_sample={result['raw_sample']}")

    def _short_raw(self, value) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        text = text.replace("\r", "").replace("\n", " ")
        return text[:1000]

    def _nearby_diagnose_and_write(self, record: WorkRecord, requested_code: str, radius_m: float):
        label = self._record_label(record)
        self.stdout.write("")
        self.stdout.write(
            f"Nearby diagnostic record id={record.id} requested_code={requested_code or ''} "
            f"label={label} lat={record.latitude} lon={record.longitude} radius_m={radius_m}"
        )

        if record.latitude is None or record.longitude is None:
            self.stdout.write("ERROR: Missing coordinates")
            return

        try:
            lat = float(record.latitude)
            lon = float(record.longitude)
            sjtsk_x, sjtsk_y = wgs84_to_sjtsk(lon, lat)
        except Exception as exc:
            self.stdout.write(f"ERROR: Coordinate transform failed: {exc}")
            return

        offsets = self._nearby_offsets(radius_m)
        start = time.perf_counter()
        dmr_result = self._identify_diagnostic(
            service_name="DMR 5G",
            image_server_url=DMR5G_IMAGE_SERVER,
            sjtsk_x=sjtsk_x,
            sjtsk_y=sjtsk_y,
            pixel_size=None,
        )
        dmr_center_m = dmr_result["parsed_value"]
        samples = []
        for offset_x, offset_y, label_text in offsets:
            dmp_result = self._identify_diagnostic(
                service_name="DMP OK",
                image_server_url=DMP_OK_IMAGE_SERVER,
                sjtsk_x=sjtsk_x + offset_x,
                sjtsk_y=sjtsk_y + offset_y,
                pixel_size=None,
            )
            dmp_m = dmp_result["parsed_value"]
            estimated_height_m = None
            if dmr_center_m is not None and dmp_m is not None:
                estimated_height_m = dmp_m - dmr_center_m
            samples.append(
                {
                    "offset_x": offset_x,
                    "offset_y": offset_y,
                    "label": label_text,
                    "dmp_m": dmp_m,
                    "estimated_height_m": estimated_height_m,
                    "duration_ms": dmp_result["duration_ms"],
                    "error": dmp_result["error"],
                }
            )

        duration_ms = int(round((time.perf_counter() - start) * 1000))
        valid_samples = [sample for sample in samples if sample["dmp_m"] is not None]
        best_sample = max(valid_samples, key=lambda sample: sample["dmp_m"]) if valid_samples else None
        center_sample = next((sample for sample in samples if sample["offset_x"] == 0 and sample["offset_y"] == 0), None)
        center_height_m = center_sample["estimated_height_m"] if center_sample else None
        max_height_m = best_sample["estimated_height_m"] if best_sample else None
        best_offset_m = (
            f"{best_sample['offset_x']},{best_sample['offset_y']} ({best_sample['label']})"
            if best_sample
            else ""
        )
        best_dmp_m = best_sample["dmp_m"] if best_sample else None

        self.stdout.write(
            "summary center_height_m={center_height_m} max_height_m={max_height_m} "
            "best_offset_m={best_offset_m} dmr_center_m={dmr_center_m} best_dmp_m={best_dmp_m} "
            "sample_count={sample_count} duration_ms={duration_ms} dmr_error={dmr_error}".format(
                center_height_m=self._format_num(center_height_m),
                max_height_m=self._format_num(max_height_m),
                best_offset_m=best_offset_m,
                dmr_center_m=self._format_num(dmr_center_m),
                best_dmp_m=self._format_num(best_dmp_m),
                sample_count=len(samples),
                duration_ms=duration_ms,
                dmr_error=dmr_result["error"],
            )
        )
        self.stdout.write("offset_x\toffset_y\tlabel\tdmp_m\testimated_height_m\tduration_ms\terror")
        for sample in samples:
            self.stdout.write(
                "{offset_x}\t{offset_y}\t{label}\t{dmp_m}\t{estimated_height_m}\t{duration_ms}\t{error}".format(
                    offset_x=sample["offset_x"],
                    offset_y=sample["offset_y"],
                    label=sample["label"],
                    dmp_m=self._format_num(sample["dmp_m"]),
                    estimated_height_m=self._format_num(sample["estimated_height_m"]),
                    duration_ms=sample["duration_ms"],
                    error=sample["error"],
                )
            )

    def _nearby_offsets(self, radius_m: float) -> list[tuple[float, float, str]]:
        offsets = [
            (0.0, 0.0, "center"),
            (0.0, 2.0, "N2"),
            (0.0, -2.0, "S2"),
            (2.0, 0.0, "E2"),
            (-2.0, 0.0, "W2"),
            (2.0, 2.0, "NE2"),
            (-2.0, 2.0, "NW2"),
            (2.0, -2.0, "SE2"),
            (-2.0, -2.0, "SW2"),
        ]
        if radius_m >= 4:
            offsets.extend(
                [
                    (0.0, 4.0, "N4"),
                    (0.0, -4.0, "S4"),
                    (4.0, 0.0, "E4"),
                    (-4.0, 0.0, "W4"),
                ]
            )
        return [
            (offset_x, offset_y, label)
            for offset_x, offset_y, label in offsets
            if offset_x * offset_x + offset_y * offset_y <= radius_m * radius_m + 1e-9
        ]

    def _format_num(self, value):
        if value is None:
            return ""
        return round(value, 3)
