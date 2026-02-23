from __future__ import annotations

from decimal import Decimal
from typing import Any


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
    base_price = _base_price_from_area(area_m2)
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
