import os
import urllib.parse
import logging
from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse, FileResponse, HttpResponse, JsonResponse
from django.contrib.staticfiles import finders
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _resolve_pmtiles(path):
    lookup = f"tiles/{path}"
    finder_path = finders.find(lookup)
    fallback_root = Path(settings.BASE_DIR) / "static" / "tiles"
    fallback_path = fallback_root / path
    resolved_path = None

    if finder_path and os.path.isfile(finder_path):
        resolved_path = finder_path
    elif fallback_path.is_file():
        resolved_path = str(fallback_path)
    return {
        "lookup": lookup,
        "finder_path": finder_path,
        "fallback_path": str(fallback_path),
        "resolved_path": resolved_path,
    }


@login_required
def pmtiles_range_serve(request, filename: str, *args, **kwargs):
    """
    Serve PMTiles with HTTP Range support (pmtiles.js / MapLibre).
    """
    resolution = _resolve_pmtiles(filename)
    static_path = resolution["resolved_path"]
    if not static_path:
        msg = (
            f"PMTiles not found: {resolution['lookup']} "
            f"(finder={resolution['finder_path'] or 'None'} fallback={resolution['fallback_path']})"
        )
        logger.warning(msg)
        return HttpResponse(msg, status=404)

    file_size = os.path.getsize(static_path)
    last_modified = os.path.getmtime(static_path)
    etag_value = f"\"{int(last_modified)}-{file_size}\""
    range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
    if_none_match = request.headers.get("If-None-Match") or request.META.get("HTTP_IF_NONE_MATCH")
    if_range = request.headers.get("If-Range") or request.META.get("HTTP_IF_RANGE")
    content_type = "application/octet-stream"
    range_header_sent = bool(range_header)
    range_request = False
    if range_header and range_header.startswith("bytes="):
        if if_range and if_range != etag_value:
            range_header = None
        else:
            range_request = True

    def _apply_common_headers(resp, length=None):
        resp["Cache-Control"] = "public, max-age=3600"
        resp["ETag"] = etag_value
        resp["Accept-Ranges"] = "bytes"
        if length is not None:
            resp["Content-Length"] = str(length)
        return resp

    def _quick_respond(status):
        resp = HttpResponse(status=status)
        return _apply_common_headers(resp)

    if not range_request and not range_header_sent and if_none_match == etag_value:
        return _quick_respond(304)

    if range_request:
        try:
            range_value = range_header.split("=", 1)[1]
            start_str, end_str = (range_value.split("-", 1) + [""])[:2]
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, IndexError):
            return _quick_respond(416)

        if start < 0 or end < start or end >= file_size:
            return _quick_respond(416)

        if request.method == "HEAD":
            resp = HttpResponse(status=206, content_type=content_type)
        else:
            def range_stream():
                with open(static_path, "rb") as f:
                    f.seek(start)
                    remaining = end - start + 1
                    chunk_size = 8192
                    while remaining > 0:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            resp = StreamingHttpResponse(range_stream(), status=206, content_type=content_type)

        resp = _apply_common_headers(resp, end - start + 1)
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return resp

    if request.method == "HEAD":
        response = HttpResponse(status=200, content_type=content_type)
    else:
        response = FileResponse(open(static_path, "rb"), content_type=content_type)
    response = _apply_common_headers(response, file_size)
    return response


@login_required
@require_GET
def pmtiles_debug(request):
    """
    Dev helper: report pmtiles presence and range support. DEBUG only.
    """
    if not settings.DEBUG:
        return HttpResponse(status=404)
    target = request.GET.get("path") or "cz.pmtiles"
    resolution = _resolve_pmtiles(target)
    exists = resolution["resolved_path"] is not None
    size = os.path.getsize(resolution["resolved_path"]) if exists else None
    headers = {
        "content_length": str(size) if size is not None else None,
        "accept_ranges": "bytes" if exists else None,
    }
    range_status = 206 if exists else None
    return JsonResponse(
        {
            "lookup": resolution["lookup"],
            "exists": exists,
            "finder_path": resolution["finder_path"],
            "fallback_path": resolution["fallback_path"],
            "abs_path": resolution["resolved_path"],
            "size": size,
            "head_headers": headers,
            "range_status": range_status,
        }
    )


@login_required
@require_GET
def glyph_debug(request):
    """
    Dev helper: HEAD a glyph URL to check availability. DEBUG only.
    """
    if not settings.DEBUG:
        return HttpResponse(status=404)
    font = request.GET.get("font") or "Open Sans Regular"
    font_enc = urllib.parse.quote(font)
    glyph_url = f"https://fonts.openmaptiles.org/{font_enc}/0-255.pbf"
    import requests

    try:
        resp = requests.head(glyph_url, timeout=5)
        status = resp.status_code
        headers = {k.lower(): v for k, v in resp.headers.items()}
    except Exception as exc:  # pragma: no cover - dev helper
        status = None
        headers = {"error": str(exc)}
    return JsonResponse({"glyph_url": glyph_url, "status": status, "headers": headers})


@login_required
@require_GET
def tiles_debug_whereis(request, filename: str, *args, **kwargs):
    """
    DEBUG-only helper that reports where the /tiles/ handler would look for a PMTiles file.
    """
    if not settings.DEBUG:
        return HttpResponse(status=404)

    resolution = _resolve_pmtiles(filename)
    fallback_exists = Path(resolution["fallback_path"]).is_file()
    staticfiles_dirs = [str(entry) for entry in (settings.STATICFILES_DIRS or [])]

    return JsonResponse(
        {
            "finder_path": resolution["finder_path"],
            "fallback_path": resolution["fallback_path"],
            "exists_fallback": fallback_exists,
            "static_url": settings.STATIC_URL,
            "staticfiles_dirs": staticfiles_dirs,
            "static_root": settings.STATIC_ROOT,
        }
    )
