from django.shortcuts import get_object_or_404
from .models import Project, ProjectMembership

def user_projects_qs(user, roles=None):
    qs = Project.objects.filter(memberships__user=user)
    if roles:
        qs = qs.filter(memberships__role__in=roles)
    return qs.distinct()

def user_can_view_project(user, project_id):
    return ProjectMembership.objects.filter(user=user, project_id=project_id).exists()

def user_is_foreman(user, project_id):
    return ProjectMembership.objects.filter(user=user, project_id=project_id, role=ProjectMembership.Role.FOREMAN).exists()

def get_project_or_404_for_user(user, project_id):
    # vyhodí 404, pokud uživatel nemá k projektu přístup
    return get_object_or_404(Project, id=project_id, memberships__user=user)

def get_visible_workrecords_qs(user):
    # všechny záznamy z projektů, kam má user přístup
    return Project.objects.filter(memberships__user=user).values_list("id", flat=True)
