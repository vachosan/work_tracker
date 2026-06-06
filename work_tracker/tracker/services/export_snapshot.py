import os

from django.db.models import Prefetch

from ..models import (
    PhotoDocumentation,
    ShrubAssessment,
    TreeAssessment,
    TreeIntervention,
)


def prepare_tree_export_queryset(work_records):
    return work_records.prefetch_related(
        Prefetch(
            "assessments",
            queryset=TreeAssessment.objects.order_by("-assessed_at", "-id"),
            to_attr="export_assessments",
        ),
        Prefetch(
            "shrub_assessments",
            queryset=ShrubAssessment.objects.order_by("-assessed_at", "-id"),
            to_attr="export_shrub_assessments",
        ),
        Prefetch(
            "interventions",
            queryset=TreeIntervention.objects.select_related(
                "intervention_type",
                "assigned_to",
            ).order_by("status", "urgency", "due_date", "id"),
            to_attr="export_interventions",
        ),
        Prefetch(
            "photos",
            queryset=PhotoDocumentation.objects.order_by("id"),
            to_attr="export_photos",
        ),
    )


def _photo_url(photo):
    if not photo.photo:
        return ""
    try:
        return photo.photo.url
    except Exception:
        return ""


def _photo_name(photo):
    if not photo.photo:
        return ""
    return os.path.basename(photo.photo.name or "")


def _assessment_snapshot(assessment):
    if assessment is None:
        return None
    return {
        "assessed_at": assessment.assessed_at,
        "dbh_cm": assessment.dbh_cm,
        "stem_circumference_cm": assessment.stem_circumference_cm,
        "stem_diameters_cm_list": assessment.stem_diameters_cm_list,
        "stem_circumferences_cm_list": assessment.stem_circumferences_cm_list,
        "height_m": assessment.height_m,
        "crown_width_m": assessment.crown_width_m,
        "crown_area_m2": assessment.crown_area_m2,
        "physiological_age": assessment.physiological_age,
        "physiological_age_label": assessment.get_physiological_age_display()
        if assessment.physiological_age is not None
        else "",
        "vitality": assessment.vitality,
        "vitality_label": assessment.get_vitality_display()
        if assessment.vitality is not None
        else "",
        "health_state": assessment.health_state,
        "health_state_label": assessment.get_health_state_display()
        if assessment.health_state is not None
        else "",
        "stability": assessment.stability,
        "stability_label": assessment.get_stability_display()
        if assessment.stability is not None
        else "",
        "access_obstacle_level": assessment.access_obstacle_level,
        "access_obstacle_label": assessment.get_access_obstacle_level_display(),
        "mistletoe_level": assessment.mistletoe_level,
        "mistletoe_label": assessment.get_mistletoe_level_display()
        if assessment.mistletoe_level is not None
        else "",
        "perspective": assessment.perspective,
        "perspective_label": assessment.get_perspective_display()
        if assessment.perspective
        else "",
    }


def _shrub_assessment_snapshot(assessment):
    if assessment is None:
        return None
    return {
        "assessed_at": assessment.assessed_at,
        "vitality": assessment.vitality,
        "vitality_label": assessment.get_vitality_display()
        if assessment.vitality is not None
        else "",
        "height_m": assessment.height_m,
        "width_m": assessment.width_m,
        "note": assessment.note,
    }


def build_tree_export_snapshot(record, project):
    assessments = getattr(record, "export_assessments", None)
    if assessments is None:
        assessments = list(record.assessments.order_by("-assessed_at", "-id")[:1])
    shrub_assessments = getattr(record, "export_shrub_assessments", None)
    if shrub_assessments is None:
        shrub_assessments = list(
            record.shrub_assessments.order_by("-assessed_at", "-id")[:1]
        )
    interventions = getattr(record, "export_interventions", None)
    if interventions is None:
        interventions = list(
            record.interventions.select_related(
                "intervention_type",
                "assigned_to",
            ).order_by("status", "urgency", "due_date", "id")
        )
    photos = getattr(record, "export_photos", None)
    if photos is None:
        photos = list(record.photos.order_by("id"))

    intervention_data = [
        {
            "type_id": intervention.intervention_type_id,
            "code": intervention.intervention_type.code,
            "name": intervention.intervention_type.name,
            "category": intervention.intervention_type.category,
            "type_description": intervention.intervention_type.description,
            "description": intervention.description,
            "urgency": intervention.urgency,
            "urgency_label": intervention.get_urgency_display(),
            "status": intervention.status,
            "status_label": intervention.get_status_display(),
            "due_date": intervention.due_date,
            "status_note": intervention.status_note,
            "estimated_price_czk": intervention.estimated_price_czk,
            "assigned_to": (
                intervention.assigned_to.get_full_name()
                or intervention.assigned_to.get_username()
                if intervention.assigned_to
                else ""
            ),
        }
        for intervention in interventions
    ]
    photo_data = [
        {
            "url": _photo_url(photo),
            "name": _photo_name(photo),
            "storage_name": photo.photo.name or "",
            "description": photo.description,
            "photo_date": photo.photo_date,
            "created_at": photo.created_at,
        }
        for photo in photos
        if photo.photo
    ]

    return {
        "work_record_id": record.pk,
        "project_id": project.pk,
        "project_name": project.name,
        "preferred_id_label": record.preferred_id_label,
        "title": record.title,
        "external_tree_id": record.external_tree_id,
        "passport_code": record.passport_code,
        "passport_no": record.passport_no,
        "vegetation_type": record.vegetation_type,
        "vegetation_type_label": record.get_vegetation_type_display()
        if record.vegetation_type
        else "",
        "taxon": record.taxon,
        "taxon_czech": record.taxon_czech,
        "taxon_latin": record.taxon_latin,
        "description": record.description,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "date": record.date,
        "created_at": record.created_at,
        "parcel_number": record.parcel_number,
        "cadastral_area_code": record.cadastral_area_code,
        "cadastral_area_name": record.cadastral_area_name,
        "municipality_code": record.municipality_code,
        "municipality_name": record.municipality_name,
        "lv_number": record.lv_number,
        "cad_lookup_status": record.cad_lookup_status,
        "cad_lookup_at": record.cad_lookup_at,
        "assessment": _assessment_snapshot(assessments[0] if assessments else None),
        "shrub_assessment": _shrub_assessment_snapshot(
            shrub_assessments[0] if shrub_assessments else None
        ),
        "interventions": intervention_data,
        "intervention_count": len(intervention_data),
        "photos": photo_data,
        "photo_count": len(photo_data),
    }
