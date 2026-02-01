from django import template

register = template.Library()


@register.filter
def csv_with_spaces(value):
    if not value:
        return ""
    parts = [part.strip() for part in str(value).split(",")]
    parts = [part for part in parts if part]
    return ", ".join(parts)
