from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q

from .models import PriceListItem, PriceListVersion


BASE_PRICE_BANDS = [
    (50, 2000),
    (100, 3500),
    (200, 5500),
    (300, 7500),
    (400, 9500),
    (500, 11500),
    (600, 13500),
    (float("inf"), 15500),
]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _base_price_from_area(area_m2: float | None) -> int | None:
    if area_m2 is None:
        return None
    if area_m2 <= 0:
        return None
    for max_area, price in BASE_PRICE_BANDS:
        if area_m2 <= max_area:
            return int(price)
    return None


def _format_band_label(min_val: int | None, max_val: int | None) -> str:
    if min_val is None and max_val is None:
        return ""
    if max_val is None:
        return f"{min_val}–"
    return f"{min_val}–{max_val}"


def _map_intervention_operation_type(intervention) -> tuple[str, str, str | None]:
    code = ""
    name = ""
    intervention_type = getattr(intervention, "intervention_type", None)
    if intervention_type:
        code = (getattr(intervention_type, "code", "") or "").strip()
        name = (getattr(intervention_type, "name", "") or "").strip()

    norm_code = code.upper()
    if norm_code:
        if "RZ" in norm_code or norm_code.endswith("RZ") or norm_code == "S-RZ":
            return "zdravotni", "code", code
        if "RB" in norm_code or "R-B" in norm_code or norm_code == "S-RB":
            return "bezpecnostni", "code", code
        if "RL" in norm_code or "R-L" in norm_code:
            return "lokalni", "code", code
        if "RO" in norm_code or "R-O" in norm_code:
            return "obvodova", "code", code
        if "SSK" in norm_code:
            return "obvodova", "code", code

    norm_name = (name or "").lower()
    if norm_name:
        if "zdravot" in norm_name:
            return "zdravotni", "name", name
        if "bezpečnost" in norm_name:
            return "bezpecnostni", "name", name
        if "lokáln" in norm_name:
            return "lokalni", "name", name
        if (
            "obvod" in norm_name
            or "sekundární koruny" in norm_name
            or "sekundarni koruny" in norm_name
            or "stabilizace" in norm_name
        ):
            return "obvodova", "name", name

    return "zdravotni", "fallback", code or name or None


def _lookup_noo_base_price(area_m2: float | None, operation_type: str) -> tuple[int | None, dict]:
    if area_m2 is None:
        return None, {
            "base_price_source": "fallback",
            "base_price_item_code": None,
            "base_price_operation_type": operation_type,
            "base_price_band": None,
            "mapped_operation_type_source": None,
            "mapped_operation_type_raw": None,
        }
    version = PriceListVersion.objects.filter(code="NOO_2026").first()
    if not version:
        return None, {
            "base_price_source": "fallback",
            "base_price_item_code": None,
            "base_price_operation_type": operation_type,
            "base_price_band": None,
            "mapped_operation_type_source": None,
            "mapped_operation_type_raw": None,
        }
    item = (
        PriceListItem.objects.filter(
            version=version,
            activity_code="ZE41",
            is_combo=False,
            operation_type=operation_type,
            band_min_m2__isnull=False,
        )
        .filter(Q(band_max_m2__isnull=True) | Q(band_max_m2__gte=area_m2))
        .filter(band_min_m2__lte=area_m2)
        .order_by("band_min_m2")
        .first()
    )
    if not item:
        return None, {
            "base_price_source": "fallback",
            "base_price_item_code": None,
            "base_price_operation_type": operation_type,
            "base_price_band": None,
            "mapped_operation_type_source": None,
            "mapped_operation_type_raw": None,
        }
    return int(item.price_czk), {
        "base_price_source": "NOO_DB",
        "base_price_item_code": item.item_code,
        "base_price_operation_type": operation_type,
        "base_price_band": _format_band_label(item.band_min_m2, item.band_max_m2),
        "mapped_operation_type_source": None,
        "mapped_operation_type_raw": None,
    }


def estimate_intervention_price(intervention) -> tuple[int | None, dict]:
    assessment = getattr(intervention.tree, "latest_assessment", None)
    if not assessment:
        return None, {
            "base_price_czk": None,
            "area_m2": None,
            "combined_multiplier": None,
            "access_obstacle_multiplier": 1.00,
            "mistletoe_multiplier": 1.00,
            "estimated_price_czk": None,
            "notes": "Chybí hodnocení stromu.",
        }

    pricing = assessment.get_pricing_context()
    area_m2 = _to_float(assessment.crown_area_m2)
    if area_m2 is None:
        height = _to_float(assessment.height_m)
        width = _to_float(assessment.crown_width_m)
        if height is not None and width is not None:
            area_m2 = height * width
    operation_type, mapped_source, mapped_raw = _map_intervention_operation_type(intervention)
    base_price, base_meta = _lookup_noo_base_price(area_m2, operation_type)
    base_meta["mapped_operation_type_source"] = mapped_source
    base_meta["mapped_operation_type_raw"] = mapped_raw
    if base_price is None:
        base_price = _base_price_from_area(area_m2)
        if base_price is not None:
            base_meta = {
                "base_price_source": "fallback",
                "base_price_item_code": None,
                "base_price_operation_type": operation_type,
                "base_price_band": None,
                "mapped_operation_type_source": mapped_source,
                "mapped_operation_type_raw": mapped_raw,
            }
    combined = pricing.get("combined_multiplier")
    if base_price is None:
        estimated = None
        notes = "Chybí data pro výpočet plochy koruny."
    elif combined is None:
        estimated = None
        notes = "Chybí multiplikátory hodnocení."
    else:
        estimated = int(round(base_price * combined))
        notes = ""

    breakdown = {
        "base_price_czk": base_price,
        "area_m2": area_m2,
        "combined_multiplier": combined,
        "access_obstacle_multiplier": pricing.get("access_obstacle_multiplier", 1.00),
        "mistletoe_multiplier": pricing.get("mistletoe_multiplier", 1.00),
        "estimated_price_czk": estimated,
        "notes": notes,
        **base_meta,
    }
    return estimated, breakdown


def apply_intervention_estimate(intervention) -> None:
    estimated, breakdown = estimate_intervention_price(intervention)
    current_estimated = getattr(intervention, "estimated_price_czk", None)
    current_breakdown = getattr(intervention, "estimated_price_breakdown", None)
    if current_estimated == estimated and current_breakdown == breakdown:
        return
    intervention.__class__.objects.filter(pk=intervention.pk).update(
        estimated_price_czk=estimated,
        estimated_price_breakdown=breakdown,
    )
