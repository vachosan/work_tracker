from django.shortcuts import get_object_or_404
from .models import Project, ProjectMembership

def user_projects_qs(user, roles=None):
    if user.is_superuser:
        return Project.objects.all()
    qs = Project.objects.filter(memberships__user=user)
    if roles:
        qs = qs.filter(memberships__role__in=roles)
    return qs.distinct()

def is_project_member(user, project):
    if user.is_superuser:
        return True  # superuser has full access
    return ProjectMembership.objects.filter(user=user, project=project).exists()

def user_can_view_project(user, project_id):
    if user.is_superuser:
        return True
    return ProjectMembership.objects.filter(user=user, project_id=project_id).exists()

def can_edit_project(user, project):
    if user.is_superuser:
        return True  # superuser has full access
    return ProjectMembership.objects.filter(
        user=user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists()

def can_lock_project(user, project):
    if user.is_superuser:
        return True  # superuser has full access
    return ProjectMembership.objects.filter(
        user=user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists()

def can_delete_project(user, project):
    if user.is_superuser:
        return True  # superuser has full access
    return False

def can_purge_project(user, project):
    if user.is_superuser:
        return True  # superuser has full access
    return False

def user_is_foreman(user, project_id):
    if user.is_superuser:
        return True  # superuser has full access
    return ProjectMembership.objects.filter(user=user, project_id=project_id, role=ProjectMembership.Role.FOREMAN).exists()

def get_project_or_404_for_user(user, project_id):
    # vyhodí 404, pokud uživatel nemá k projektu přístup
    if user.is_superuser:
        return get_object_or_404(Project, id=project_id)
    return get_object_or_404(Project, id=project_id, memberships__user=user)

def get_visible_workrecords_qs(user):
    # všechny záznamy z projektů, kam má user přístup
    return user_projects_qs(user).values_list("id", flat=True)
