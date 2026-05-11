import json
import logging
import math
import time

import requests

logger = logging.getLogger(__name__)

DMR5G_IMAGE_SERVER = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer"
DMP1G_IMAGE_SERVER = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmp1g/ImageServer"
DMP_OK_IMAGE_SERVER = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmp_obrazova_korelace/ImageServer"
CUZK_HEIGHT_SOURCE = "CUZK DMP OK - DMR 5G"
DEFAULT_TIMEOUT_S = 5


class CuzkHeightError(Exception):
    pass


def _http_get_json(url: str, params: dict, timeout_s: int = DEFAULT_TIMEOUT_S) -> dict:
    try:
        response = requests.get(url, params=params, timeout=timeout_s)
        response.raise_for_status()
        return response.json()
    except requests.Timeout as exc:
        logger.warning("cuzk height request timeout url=%s", url)
        raise CuzkHeightError("Dotaz na ČÚZK vypršel.") from exc
    except requests.RequestException as exc:
        logger.warning("cuzk height request failed url=%s error=%s", url, exc)
        raise CuzkHeightError("Dotaz na ČÚZK selhal.") from exc
    except ValueError as exc:
        logger.warning("cuzk height invalid json url=%s error=%s", url, exc)
        raise CuzkHeightError("ČÚZK vrátil neplatnou JSON odpověď.") from exc


def wgs84_to_sjtsk(lon: float, lat: float) -> tuple[float, float]:
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
        raise CuzkHeightError("Souřadnice se nepodařilo převést do S-JTSK.")
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


def _parse_pixel_value(payload: dict, service_label: str) -> float:
    if "error" in payload:
        message = payload["error"].get("message") if isinstance(payload["error"], dict) else None
        raise CuzkHeightError(f"ČÚZK {service_label} vrátil chybu: {message or 'neznámá chyba'}.")

    raw_value = payload.get("value")
    if raw_value in (None, "", "NoData", "NaN"):
        raise CuzkHeightError(f"ČÚZK {service_label} nevrátil výškovou hodnotu pro daný bod.")

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise CuzkHeightError(f"ČÚZK {service_label} vrátil nečíselnou hodnotu.") from exc

    if not math.isfinite(value):
        raise CuzkHeightError(f"ČÚZK {service_label} vrátil neplatnou hodnotu.")
    return value


def get_image_server_pixel_value(
    image_server_url: str,
    sjtsk_x: float,
    sjtsk_y: float,
    service_label: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> float:
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
    }
    payload = _http_get_json(identify_url, params=params, timeout_s=timeout_s)
    return _parse_pixel_value(payload, service_label)


def estimate_tree_height_from_cuzk(lat: float, lon: float) -> dict:
    start = time.perf_counter()
    sjtsk_x, sjtsk_y = wgs84_to_sjtsk(lon, lat)
    dmr_m = get_image_server_pixel_value(DMR5G_IMAGE_SERVER, sjtsk_x, sjtsk_y, "DMR 5G")
    dmp_m = get_image_server_pixel_value(DMP_OK_IMAGE_SERVER, sjtsk_x, sjtsk_y, "DMP OK")
    estimated_height_m = dmp_m - dmr_m
    duration_ms = int(round((time.perf_counter() - start) * 1000))

    warnings = []
    if estimated_height_m < 0:
        warnings.append("Odhad výšky je záporný; bod nemusí ležet na koruně stromu nebo data nejsou vhodná.")
    elif estimated_height_m > 100:
        warnings.append("Odhad výšky je extrémně vysoký; výsledek berte jako podezřelý.")

    return {
        "ok": True,
        "dmr_m": round(dmr_m, 3),
        "dmp_m": round(dmp_m, 3),
        "estimated_height_m": round(estimated_height_m, 3),
        "duration_ms": duration_ms,
        "source": CUZK_HEIGHT_SOURCE,
        "sjtsk_x": sjtsk_x,
        "sjtsk_y": sjtsk_y,
        "warnings": warnings,
    }
