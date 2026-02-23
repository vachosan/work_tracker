import json

from django import template
from django.utils.safestring import mark_safe

from tracker.models import (
    HEALTH_STATE_CHOICES,
    PHYSIOLOGICAL_AGE_CHOICES,
    PERSPECTIVE_CHOICES,
    STABILITY_CHOICES,
    VITALITY_CHOICES,
    ACCESS_OBSTACLE_LEVEL_CHOICES,
    MISTLETOE_LEVELS,
)

register = template.Library()


@register.filter
def csv_with_spaces(value):
    if not value:
        return ""
    parts = [part.strip() for part in str(value).split(",")]
    parts = [part for part in parts if part]
    return ", ".join(parts)


def _choices_to_map(choices):
    return {str(value): label for value, label in choices}


@register.simple_tag
def assessment_scales_json():
    data = {
        "physiological_age": _choices_to_map(PHYSIOLOGICAL_AGE_CHOICES),
        "vitality": _choices_to_map(VITALITY_CHOICES),
        "health_state": _choices_to_map(HEALTH_STATE_CHOICES),
        "stability": _choices_to_map(STABILITY_CHOICES),
        "perspective": _choices_to_map(PERSPECTIVE_CHOICES),
        "access_obstacle_level": _choices_to_map(ACCESS_OBSTACLE_LEVEL_CHOICES),
    }
    return mark_safe(json.dumps(data, ensure_ascii=False))


@register.simple_tag
def mistletoe_scales_json():
    data = {"0": {"label": "bez jmelí"}}
    data.update({str(key): value for key, value in MISTLETOE_LEVELS.items()})
    return mark_safe(json.dumps(data, ensure_ascii=False))


@register.filter
def mistletoe_label(value):
    if value in (None, ""):
        return ""
    try:
        key = int(value)
    except (TypeError, ValueError):
        return ""
    info = MISTLETOE_LEVELS.get(key)
    if not info:
        return ""
    return f"{info['code']} – {info['label']} ({info['range']} objemu koruny)"
