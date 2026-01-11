import os
import io
import zipfile
import csv
import datetime as dt
import xml.etree.ElementTree as ET
import unicodedata
import re
import tempfile
from urllib.parse import urlencode
import zipstream
import json
import requests
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Max, Min, F, Count, Q, Prefetch, Exists, OuterRef
from django.http import (
    StreamingHttpResponse,
    FileResponse,
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponse,
)
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from PIL import Image

from .forms import (
    WorkRecordForm,
    PhotoDocumentationForm,
    ProjectForm,
    CustomUserCreationForm,
    ProjectEditForm,
    AddMemberForm,
    TreeInterventionForm,
)
from .models import (
    Project,
    WorkRecord,
    PhotoDocumentation,
    ProjectMembership,
    TreeAssessment,
    TreeIntervention,
    Species,
)
from .permissions import (
    user_projects_qs,
    user_can_view_project,
    user_is_foreman,
    get_project_or_404_for_user,
)

# ------------------ Auth / základní stránky ------------------

def logout_view(request):
    logout(request)
    return redirect('login')

def home(request):
    return render(request, 'home.html')

def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

# ------------------ Projekty ------------------

@login_required
def project_detail(request, pk):
    """Stránka všech úkonů projektu + vyhledávání, filtry, stránkování."""
    project = get_object_or_404(Project, pk=pk)

    # práva
    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    qs = project.trees.all()

    # filtry (GET)
    q = request.GET.get('q', '').strip()
    df = parse_date(request.GET.get('date_from') or '')
    dt = parse_date(request.GET.get('date_to') or '')
    has_assessment = request.GET.get('has_assessment', '').strip()
    has_open_interventions = request.GET.get('has_open_interventions', '').strip()

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if df:
        qs = qs.filter(date__gte=df)
    if dt:
        qs = qs.filter(date__lte=dt)

    # filtr podle hodnocení
    if has_assessment == "yes":
        qs = qs.filter(assessments__isnull=False).distinct()
    elif has_assessment == "no":
        qs = qs.filter(assessments__isnull=True)

    # filtr podle zásahů
    if has_open_interventions == "none":
        # úkony bez jakéhokoli zásahu
        qs = qs.filter(interventions__isnull=True)
    elif has_open_interventions == "proposed":
        # alespoň jeden zásah ve stavu draft/pending_approval
        qs = qs.filter(
            interventions__status__in=["draft", "pending_approval"]
        ).distinct()
    elif has_open_interventions == "approved":
        # alespoň jeden zásah ve stavu approved
        qs = qs.filter(interventions__status="approved").distinct()
    elif has_open_interventions == "handover":
        # alespoň jeden zásah ve stavu pending_check
        qs = qs.filter(interventions__status="pending_check").distinct()
    elif has_open_interventions == "completed":
        # alespoň jeden zásah ve stavu completed
        qs = qs.filter(interventions__status="completed").distinct()

    # přednačtení souvisejících dat pro souhrny
    latest_assessments_qs = TreeAssessment.objects.order_by("-assessed_at", "-id")
    interventions_qs = TreeIntervention.objects.order_by("urgency", "due_date", "id")

    qs = (
        qs.select_related("project")
        .prefetch_related(
            Prefetch("assessments", queryset=latest_assessments_qs, to_attr="prefetched_assessments"),
            Prefetch("interventions", queryset=interventions_qs, to_attr="prefetched_interventions"),
        )
        .order_by("-created_at")
    )

    # stránkování
    paginator = Paginator(qs, 20)  # 20 na stránku
    page_obj = paginator.get_page(request.GET.get("page"))

    # dopočítání souhrnů pro řádky
    for wr in page_obj.object_list:
        # latest_assessment je @property na WorkRecord, nepřepisujeme ho zde.
        interventions = list(getattr(wr, "prefetched_interventions", []))
        wr.intervention_count = len(interventions)
        wr.open_intervention_count = sum(1 for i in interventions if i.status != "completed")
        wr.max_urgency = max((i.urgency for i in interventions), default=None) if interventions else None

        # podrobnější přehled stavů zásahů
        wr.interventions_proposed = 0
        wr.interventions_approved = 0
        wr.interventions_handover = 0
        wr.interventions_completed = 0

        for iv in interventions:
            if iv.status in ["draft", "pending_approval"]:
                wr.interventions_proposed += 1
            elif iv.status == "approved":
                wr.interventions_approved += 1
            elif iv.status == "pending_check":
                wr.interventions_handover += 1
            elif iv.status == "completed":
                wr.interventions_completed += 1

    # flagy pro šablonu (tlačítka)
    is_foreman = ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists()
    is_member = ProjectMembership.objects.filter(user=request.user, project=project).exists()

    return render(
        request,
        "tracker/project_detail.html",
        {
            "project": project,
            "page_obj": page_obj,
            "q": q,
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
            "has_assessment": has_assessment,
            "has_open_interventions": has_open_interventions,
            "is_foreman": is_foreman,
            "is_member": is_member,
        },
    )

@login_required
def edit_project(request, pk):
    project = get_object_or_404(Project, pk=pk)

    # Jen stavbyvedoucí
    if not ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists():
        return redirect('work_record_list')

    project_form = ProjectEditForm(instance=project)
    add_member_form = AddMemberForm()

    if request.method == 'POST':
        if 'save_project' in request.POST:
            project_form = ProjectEditForm(request.POST, instance=project)
            if project_form.is_valid():
                project_form.save()
                return redirect('work_record_list')

        elif 'add_member' in request.POST:
            add_member_form = AddMemberForm(request.POST)
            if add_member_form.is_valid():
                user = add_member_form.cleaned_data['user']
                role = add_member_form.cleaned_data['role']
                ProjectMembership.objects.get_or_create(
                    user=user,
                    project=project,
                    defaults={'role': role}
                )
                return redirect('edit_project', pk=pk)

    members = ProjectMembership.objects.filter(project=project).select_related('user')

    return render(request, 'tracker/edit_project.html', {
        'project': project,
        'project_form': project_form,
        'add_member_form': add_member_form,
        'members': members,
    })


@login_required
def remove_member(request, pk, user_id):
    project = get_object_or_404(Project, pk=pk)

    if not ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists():
        return redirect('work_record_list')

    ProjectMembership.objects.filter(user_id=user_id, project=project).delete()
    return redirect('edit_project', pk=pk)


@login_required
def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.is_closed = False
            project.save()

            # autor = FOREMAN
            ProjectMembership.objects.get_or_create(
                user=request.user,
                project=project,
                defaults={"role": ProjectMembership.Role.FOREMAN},
            )

            return redirect('work_record_list')
    else:
        form = ProjectForm()
    return render(request, 'tracker/create_project.html', {'form': form})


@login_required
def close_project(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists():
        return redirect('work_record_list')
    project.is_closed = True
    project.save()
    return redirect('work_record_list')


@login_required
def activate_project(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists():
        return redirect('work_record_list')
    project.is_closed = False
    project.save()
    return redirect('closed_projects_list')


@login_required
def closed_projects_list(request):
    projects = (
        user_projects_qs(request.user)
        .filter(is_closed=True)
        .annotate(latest_work_time=Max('work_records__created_at'))
        .order_by(F('latest_work_time').desc(nulls_last=True), '-id')
    )

    # flag pro šablonu (zobrazit tlačítka jen foremanovi)
    for p in projects:
        p.is_foreman = ProjectMembership.objects.filter(
            user=request.user, project=p, role=ProjectMembership.Role.FOREMAN
        ).exists()

    return render(request, 'tracker/closed_projects_list.html', {'projects': projects})

# ------------------ WorkRecord ------------------

@login_required
def work_record_list(request):
    latest_wr = WorkRecord.objects.order_by('-created_at')  # pro pořadí v prefetchi

    projects = (
        user_projects_qs(request.user)
        .filter(is_closed=False)
        .annotate(
            latest_work_time=Max('work_records__created_at'),
            trees_count=Count('trees', distinct=True)
        )
        .order_by(F('latest_work_time').desc(nulls_last=True), '-id')
        .prefetch_related(
            Prefetch('work_records', queryset=latest_wr)  # abychom měli nové nahoře
        )
    )

    for p in projects:
        p.is_foreman = ProjectMembership.objects.filter(
            user=request.user, project=p, role=ProjectMembership.Role.FOREMAN
        ).exists()
        p.is_member = ProjectMembership.objects.filter(
            user=request.user, project=p
        ).exists()

    return render(request, 'tracker/work_record_list.html', {
        'projects': projects,
    })

@login_required
def create_work_record(request, project_id=None):
    project_context_id = project_id or request.GET.get("project") or request.POST.get("project")
    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        if work_record_form.is_valid():
            work_record = work_record_form.save(commit=False)

            lat_str = request.POST.get("latitude") or request.GET.get("lat")
            lon_str = request.POST.get("longitude") or request.GET.get("lon")
            try:
                if lat_str is not None and lon_str is not None:
                    work_record.latitude = float(lat_str)
                    work_record.longitude = float(lon_str)
            except (TypeError, ValueError):
                pass

            work_record.save()
            work_record.sync_title_from_identifiers()
            work_record.save(
                update_fields=[
                    "title",
                    "external_tree_id",
                    "description",
                    "date",
                    "project",
                    "latitude",
                    "longitude",
                ]
            )

            # ověř přístup k projektu
            if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
                return redirect('work_record_list')

            if project_context_id:
                try:
                    project = Project.objects.get(pk=project_context_id)
                except Project.DoesNotExist:
                    return redirect('work_record_list')
                if not user_can_view_project(request.user, project.pk):
                    return redirect('work_record_list')
                project.trees.add(work_record)

            if 'photo' in request.FILES and photo_form.is_valid():
                photo = photo_form.save(commit=False)
                photo.work_record = work_record
                photo.save()

            if project_context_id:
                return redirect('project_detail', pk=project_context_id)
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        initial_data = {}
        if project_context_id:
            project = get_project_or_404_for_user(request.user, project_context_id)
            initial_data['project'] = project

        work_record_form = WorkRecordForm(initial=initial_data)
        photo_form = PhotoDocumentationForm()

    return render(request, 'tracker/create_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
        'project_context_id': project_context_id,
    })

@login_required
def delete_work_record(request, pk):
    """Smazání úkonu včetně fotek a souborů z disku."""
    work_record = get_object_or_404(WorkRecord, pk=pk)

    # kontrola oprávnění
    if not user_can_view_project(request.user, work_record.project.pk):
        return redirect('work_record_list')

    if request.method == "POST":
        # smažeme všechny fotky
        photos = PhotoDocumentation.objects.filter(work_record=work_record)
        for photo in photos:
            if photo.photo and os.path.exists(photo.photo.path):
                try:
                    os.remove(photo.photo.path)
                except Exception as e:
                    print(f"⚠️ Nepodařilo se smazat soubor {photo.photo.path}: {e}")
            photo.delete()

        # smažeme samotný úkon
        work_record.delete()
        messages.success(request, "Úkon byl úspěšně smazán včetně fotek.")
        return redirect("project_detail", pk=work_record.project.pk)

    return render(request, "tracker/confirm_delete_work_record.html", {"work_record": work_record})

@login_required
def work_record_detail(request, pk):
    work_record = get_object_or_404(
        WorkRecord.objects
        .select_related("project")
        .prefetch_related("assessments", "photos"),
        pk=pk,
    )

    if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
        return redirect('work_record_list')

    if request.method == 'POST':
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)
        if photo_form.is_valid():
            photo = photo_form.save(commit=False)
            photo.work_record = work_record
            photo.save()
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        photo_form = PhotoDocumentationForm()

    photos = work_record.photos.all()
    valid_photos = [photo for photo in photos if photo.photo]
    interventions = work_record.interventions.select_related("intervention_type").order_by(
        "status", "urgency", "due_date", "id"
    )

    return render(request, 'tracker/work_record_detail.html', {
        'work_record': work_record,
        'photo_form': photo_form,
        'photos': valid_photos,
        'interventions': interventions,
    })


@login_required
def tree_intervention_create(request, tree_id):
    tree = get_object_or_404(WorkRecord, pk=tree_id)
    if tree.project_id and not user_can_view_project(request.user, tree.project_id):
        return redirect('work_record_list')

    form = TreeInterventionForm(request.POST or None)
    intervention_note_data_json = mark_safe(json.dumps(form.intervention_type_note_data))

    if request.method == 'POST' and form.is_valid():
        intervention = form.save(commit=False)
        intervention.tree = tree
        intervention.created_by = request.user
        intervention.save()
        messages.success(request, "Zásah byl uložen.")
        return redirect('work_record_detail', pk=tree.pk)

    return render(request, 'tracker/tree_intervention_form.html', {
        'form': form,
        'tree': tree,
        'form_title': 'Přidat zásah',
        'intervention_note_data_json': intervention_note_data_json,
    })


@login_required
def tree_intervention_update(request, pk):
    intervention = get_object_or_404(TreeIntervention, pk=pk)
    tree = intervention.tree
    if tree.project_id and not user_can_view_project(request.user, tree.project_id):
        return redirect('work_record_list')

    form = TreeInterventionForm(request.POST or None, instance=intervention)
    intervention_note_data_json = mark_safe(json.dumps(form.intervention_type_note_data))

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Zásah byl aktualizován.")
        return redirect('work_record_detail', pk=tree.pk)

    return render(request, 'tracker/tree_intervention_form.html', {
        'form': form,
        'tree': tree,
        'intervention': intervention,
        'form_title': 'Upravit zásah',
        'intervention_note_data_json': intervention_note_data_json,
    })


@login_required
@require_http_methods(["POST"])
def tree_intervention_api(request, tree_id):
    tree = get_object_or_404(WorkRecord, pk=tree_id)
    if tree.project_id and not user_can_view_project(request.user, tree.project_id):
        return JsonResponse({'status': 'error', 'msg': 'Nemáte oprávnění.'}, status=403)

    form = TreeInterventionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'status': 'error', 'errors': form.errors.get_json_data()}, status=400)

    intervention = form.save(commit=False)
    intervention.tree = tree
    intervention.created_by = request.user
    intervention.save()

    return JsonResponse({
        'status': 'ok',
        'intervention': {
            'id': intervention.pk,
            'type': str(intervention.intervention_type),
            'code': intervention.intervention_type.code,
            'urgency': intervention.get_urgency_display(),
            'status': intervention.get_status_display(),
        },
    })


@login_required
@require_http_methods(["GET", "POST"])
def tree_intervention_api(request, tree_id):
    tree = get_object_or_404(WorkRecord, pk=tree_id)
    if tree.project_id and not user_can_view_project(request.user, tree.project_id):
        return JsonResponse({'status': 'error', 'msg': 'Nemáte oprávnění.'}, status=403)

    def serialize_intervention(obj):
        return {
            'id': obj.pk,
            'code': obj.intervention_type.code if obj.intervention_type else '',
            'name': obj.intervention_type.name if obj.intervention_type else '',
            'urgency': obj.get_urgency_display(),
            'status': obj.get_status_display(),
            'status_code': obj.status,
            'created_at': obj.created_at.isoformat() if obj.created_at else None,
            'handed_over_for_check_at': (
                obj.handed_over_for_check_at.isoformat()
                if getattr(obj, "handed_over_for_check_at", None)
                else None
            ),
        }

    if request.method == "GET":
        interventions = (
            TreeIntervention.objects
            .filter(tree=tree)
            .select_related("intervention_type")
            .order_by("status", "urgency", "due_date", "id")
        )
        data = [serialize_intervention(obj) for obj in interventions]
        return JsonResponse({'status': 'ok', 'interventions': data})

    action = request.POST.get('action')
    if action == "handover":
        try:
            intervention_id = int(request.POST.get('id') or 0)
        except (TypeError, ValueError):
            return JsonResponse({'status': 'error', 'msg': 'Neplatné ID zásahu.'}, status=400)

        intervention = get_object_or_404(
            TreeIntervention.objects.select_related("intervention_type"),
            pk=intervention_id,
            tree=tree,
        )
        if intervention.status not in ("approved", "in_progress"):
            return JsonResponse({'status': 'error', 'msg': 'Tento zásah nelze předat ke kontrole.'}, status=400)

        intervention.mark_handed_over_for_check()
        return JsonResponse({'status': 'ok', 'intervention': serialize_intervention(intervention)})

    form = TreeInterventionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'status': 'error', 'errors': form.errors.get_json_data()}, status=400)

    intervention = form.save(commit=False)
    intervention.tree = tree
    intervention.created_by = request.user
    intervention.save()

    return JsonResponse({'status': 'ok', 'intervention': serialize_intervention(intervention)})


@login_required
def edit_work_record(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)

    # přístup jen pro členy projektu
    if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
        return redirect('work_record_list')

    work_record_form = WorkRecordForm(instance=work_record)
    photo_form = PhotoDocumentationForm()

    if request.method == 'POST':
        if 'save_work_record' in request.POST:
            work_record_form = WorkRecordForm(request.POST, instance=work_record)
            if work_record_form.is_valid():
                work_record = work_record_form.save(commit=False)
                work_record.sync_title_from_identifiers()
                work_record.save()
                from django.urls import reverse
                url = reverse('work_record_list')
                if work_record.project_id:
                    url = f"{url}#project-{work_record.project_id}"
                return redirect(url)

        elif 'add_photo' in request.POST:
            photo_form = PhotoDocumentationForm(request.POST, request.FILES)
            if 'photo' in request.FILES and photo_form.is_valid():
                photo = photo_form.save(commit=False)
                photo.work_record = work_record
                photo.save()
            return redirect('edit_work_record', pk=work_record.pk)

    photos = work_record.photos.all()

    return render(request, 'tracker/edit_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
        'photos': photos,
        'work_record': work_record,
    })

# ------------------ Fotky ------------------

@login_required
def add_photo(request, work_record_id):
    work_record = get_object_or_404(WorkRecord, pk=work_record_id)

    if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
        return redirect('work_record_list')

    if request.method == "POST":
        form = PhotoDocumentationForm(request.POST, request.FILES)
        photo = request.FILES.get("photo")

        if not photo:
            default_photo_path = os.path.join(settings.MEDIA_ROOT, "photos", "default.jpg")
            with open(default_photo_path, 'rb') as default_file:
                photo = File(default_file, name="default.jpg")

        if form.is_valid():
            new_photo = form.save(commit=False)
            new_photo.work_record = work_record
            new_photo.photo = photo
            new_photo.save()

    return redirect("work_record_detail", pk=work_record_id)


@login_required
def delete_photo(request, pk):
    photo = get_object_or_404(PhotoDocumentation, pk=pk)

    if photo.work_record.project_id and not user_can_view_project(request.user, photo.work_record.project_id):
        return redirect('work_record_list')

    work_record_pk = photo.work_record.pk
    photo.delete()
    return redirect('edit_work_record', pk=work_record_pk)




def _slugify_export_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^a-zA-Z0-9_-]+', '_', name)
    return name.strip('_') or 'ukon'


def _get_export_work_records(request, project):
    export_all_requested = bool(request.POST.get("export_all"))
    if export_all_requested:
        return project.trees.all(), None

    selected_ids = request.POST.getlist("selected_records")
    if not selected_ids:
        messages.warning(request, "Vyberte prosim alespon jeden zaznam pro export.")
        return None, redirect("project_detail", pk=project.pk)

    return project.trees.filter(id__in=selected_ids), None


def _build_export_queryset(work_records):
    latest_assessments_qs = TreeAssessment.objects.order_by("-assessed_at", "-id")
    return (
        work_records.select_related("project")
        .prefetch_related(
            Prefetch(
                "assessments",
                queryset=latest_assessments_qs,
                to_attr="prefetched_assessments",
            )
        )
        .annotate(intervention_count=Count("interventions", distinct=True))
    )


def _latest_assessment_for_export(record):
    assessments = getattr(record, "prefetched_assessments", None)
    if assessments:
        return assessments[0]
    return None


@login_required
def export_selected_zip(request, pk):
    """Export vybraných nebo všech úkonů projektu jako streamovaný ZIP (nízká paměťová náročnost)."""
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    work_records, redirect_response = _get_export_work_records(request, project)
    if redirect_response:
        return redirect_response


    def file_chunks(file_obj):
        if hasattr(file_obj, "chunks"):
            for chunk in file_obj.chunks():
                if chunk:
                    yield chunk
        else:
            while True:
                chunk = file_obj.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    # vytvoření streamovacího ZIP objektu
    z = zipstream.ZipFile(mode='w', compression=zipfile.ZIP_DEFLATED)

    for record in work_records:
        folder = _slugify_export_name(record.title or f"ukon_{record.id}")
        photos = PhotoDocumentation.objects.filter(work_record=record)

        for photo in photos:
            if not photo.photo:
                continue

            base_filename = os.path.basename(photo.photo.name)
            ext = os.path.splitext(base_filename)[1] or ".jpg"

            if photo.description:
                safe_name = _slugify_export_name(photo.description)
                filename = f"{safe_name}{ext}"
            else:
                filename = base_filename

            arcname = os.path.join(folder, filename)
            storage = photo.photo.storage
            name = photo.photo.name
            local_path = None
            try:
                local_path = storage.path(name)
            except (NotImplementedError, AttributeError):
                local_path = None

            if local_path and os.path.exists(local_path):
                z.write(local_path, arcname)
                continue

            try:
                file_handle = storage.open(name, "rb")
            except Exception:
                continue

            with file_handle as f:
                z.write_iter(arcname, file_chunks(f))

    # příprava odpovědi
    today_str = date.today().strftime("%Y-%m-%d")
    filename = f'{_slugify_export_name(project.name)}_{today_str}.zip'

    response = StreamingHttpResponse(z, content_type='application/zip')
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

EXPORT_DATA_HEADERS = [
    "work_record_id",
    "project_id",
    "project_name",
    "title",
    "external_tree_id",
    "taxon",
    "taxon_czech",
    "taxon_latin",
    "latitude",
    "longitude",
    "date",
    "created_at",
    "intervention_count",
    "assessment_assessed_at",
    "assessment_dbh_cm",
    "assessment_height_m",
    "assessment_crown_width_m",
    "assessment_crown_area_m2",
    "assessment_physiological_age",
    "assessment_vitality",
    "assessment_health_state",
    "assessment_stability",
    "assessment_perspective",
]


def _export_row_native(record, assessment):
    def to_float(value):
        if value is None:
            return None
        return float(value)

    return [
        record.id,
        record.project_id,
        record.project.name if record.project else None,
        record.title or None,
        record.external_tree_id or None,
        record.taxon or None,
        record.taxon_czech or None,
        record.taxon_latin or None,
        to_float(record.latitude) if record.latitude is not None else None,
        to_float(record.longitude) if record.longitude is not None else None,
        record.date if record.date else None,
        record.created_at if record.created_at else None,
        getattr(record, "intervention_count", None),
        assessment.assessed_at if assessment and assessment.assessed_at else None,
        to_float(assessment.dbh_cm) if assessment and assessment.dbh_cm is not None else None,
        to_float(assessment.height_m) if assessment and assessment.height_m is not None else None,
        to_float(assessment.crown_width_m) if assessment and assessment.crown_width_m is not None else None,
        to_float(assessment.crown_area_m2) if assessment and assessment.crown_area_m2 is not None else None,
        assessment.physiological_age if assessment and assessment.physiological_age is not None else None,
        assessment.vitality if assessment and assessment.vitality is not None else None,
        assessment.health_state if assessment and assessment.health_state is not None else None,
        assessment.stability if assessment and assessment.stability is not None else None,
        assessment.perspective if assessment and assessment.perspective is not None else None,
    ]




@login_required
def export_selected_csv(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    work_records, redirect_response = _get_export_work_records(request, project)
    if redirect_response:
        return redirect_response

    work_records = _build_export_queryset(work_records)

    today_str = date.today().strftime("%Y-%m-%d")
    filename = f'{_slugify_export_name(project.name)}_{today_str}.csv'

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(EXPORT_DATA_HEADERS)

    for record in work_records:
        assessment = _latest_assessment_for_export(record)
        writer.writerow(
            [
                record.id,
                record.project_id or "",
                record.project.name if record.project else "",
                record.title or "",
                record.external_tree_id or "",
                record.taxon or "",
                record.taxon_czech or "",
                record.taxon_latin or "",
                record.latitude if record.latitude is not None else "",
                record.longitude if record.longitude is not None else "",
                record.date.isoformat() if record.date else "",
                record.created_at.isoformat() if record.created_at else "",
                getattr(record, "intervention_count", ""),
                assessment.assessed_at.isoformat() if assessment and assessment.assessed_at else "",
                assessment.dbh_cm if assessment and assessment.dbh_cm is not None else "",
                assessment.height_m if assessment and assessment.height_m is not None else "",
                assessment.crown_width_m if assessment and assessment.crown_width_m is not None else "",
                assessment.crown_area_m2 if assessment and assessment.crown_area_m2 is not None else "",
                assessment.physiological_age if assessment and assessment.physiological_age is not None else "",
                assessment.vitality if assessment and assessment.vitality is not None else "",
                assessment.health_state if assessment and assessment.health_state is not None else "",
                assessment.stability if assessment and assessment.stability is not None else "",
                assessment.perspective if assessment and assessment.perspective is not None else "",
            ]
        )

    return response





@login_required
def export_selected_xlsx(request, pk):
    try:
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter
    except ModuleNotFoundError:
        messages.error(
            request,
            "Export Excelu vyzaduje balicek openpyxl. Nainstalujte jej prosim.",
        )
        return redirect("project_detail", pk=pk)

    def excel_safe(value):
        if isinstance(value, dt.datetime):
            if timezone.is_aware(value):
                return timezone.localtime(value).replace(tzinfo=None)
            return value
        return value

    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    work_records, redirect_response = _get_export_work_records(request, project)
    if redirect_response:
        return redirect_response

    work_records = _build_export_queryset(work_records)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    ws.append(EXPORT_DATA_HEADERS)

    for record in work_records:
        assessment = _latest_assessment_for_export(record)
        row = _export_row_native(record, assessment)
        ws.append([excel_safe(item) for item in row])

    ws.freeze_panes = "A2"
    last_row = ws.max_row
    last_col_letter = get_column_letter(len(EXPORT_DATA_HEADERS))
    ws.auto_filter.ref = f"A1:{last_col_letter}{last_row}"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"arbomap_project_{project.pk}_data.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_selected_xml(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    work_records, redirect_response = _get_export_work_records(request, project)
    if redirect_response:
        return redirect_response

    work_records = _build_export_queryset(work_records)

    root = ET.Element("arbomap_export", generated_at=timezone.now().isoformat())
    project_el = ET.SubElement(
        root,
        "project",
        id=str(project.pk),
        name=project.name or "",
    )

    for record in work_records:
        wr_el = ET.SubElement(project_el, "work_record", id=str(record.pk))
        loc_attrs = {}
        if record.latitude is not None:
            loc_attrs["lat"] = str(record.latitude)
        if record.longitude is not None:
            loc_attrs["lon"] = str(record.longitude)
        if loc_attrs:
            ET.SubElement(wr_el, "location", **loc_attrs)

        assessment = _latest_assessment_for_export(record)
        if assessment:
            attrs = {}
            if assessment.height_m is not None:
                attrs["height_m"] = str(assessment.height_m)
            if assessment.crown_width_m is not None:
                attrs["crown_width_m"] = str(assessment.crown_width_m)
            if assessment.crown_area_m2 is not None:
                attrs["crown_area_m2"] = str(assessment.crown_area_m2)
            if assessment.dbh_cm is not None:
                attrs["dbh_cm"] = str(assessment.dbh_cm)
            if assessment.physiological_age is not None:
                attrs["physiological_age"] = str(assessment.physiological_age)
            if assessment.vitality is not None:
                attrs["vitality"] = str(assessment.vitality)
            if assessment.health_state is not None:
                attrs["health_state"] = str(assessment.health_state)
            if assessment.stability is not None:
                attrs["stability"] = str(assessment.stability)
            if assessment.perspective:
                attrs["perspective"] = assessment.perspective
            if assessment.assessed_at:
                attrs["assessed_at"] = assessment.assessed_at.isoformat()
            ET.SubElement(wr_el, "assessment", **attrs)

    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"

    filename = f"arbomap_project_{project.pk}.xml"
    response = HttpResponse(xml_bytes, content_type='application/xml; charset=utf-8')
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



"""
# ------------------ Test mapy ------------------

def map_test(request):
    # testovací souřadnice – Třinec
    context = {
        "latitude": 49.684,
        "longitude": 18.676,
        "mapy_key": settings.MAPY_API_KEY,
    }
    return render(request, "tracker/map_test.html", context)

def mapy_key_test(request):
    return JsonResponse({
        "mapy_key": settings.MAPY_API_KEY or "❌ Žádný klíč nenalezen"
    })

def mapy_geocode_test(request):
    query = request.GET.get("q", "Ostrava")
    url = "https://api.mapy.cz/v1/geocode"
    params = {"query": query, "lang": "cs", "key": settings.MAPY_API_KEY}

    r = requests.get(url, params=params)
    data = r.json()
    print(data)

    return render(request, "tracker/map_rest_test.html", {"data": data, "query": query})


"""

THUMB_MAX_SIZE = 256


@login_required
def bulk_approve_interventions(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    if request.method != "POST":
        return redirect("project_detail", pk=pk)

    selected_ids = request.POST.getlist("selected_records")
    if not selected_ids:
        messages.warning(request, "Vyberte prosím alespoň jeden strom / úkon.")
        return redirect("project_detail", pk=pk)

    work_records = project.trees.filter(id__in=selected_ids)
    interventions_qs = TreeIntervention.objects.filter(
        tree__in=work_records,
        status__in=["draft", "pending_approval"],
    )
    interventions = list(interventions_qs)

    if not interventions:
        messages.info(request, "Nebyl nalezen žádný navržený zásah ke schválení.")
        return redirect("project_detail", pk=pk)

    for intervention in interventions:
        if hasattr(intervention, "mark_approved"):
            intervention.mark_approved()
        else:
            from django.utils import timezone

            intervention.status = "approved"
            if getattr(intervention, "approved_at", None) is None:
                intervention.approved_at = timezone.now()
            intervention.save()

    messages.success(
        request,
        f"Schváleno {len(interventions)} navržených zásahů.",
    )
    return redirect("project_detail", pk=pk)


def get_photo_thumbnail(photo_obj, size=THUMB_MAX_SIZE):
    """
    Returns URL of a cached thumbnail for the given photo. Generates it on demand.
    """
    if not photo_obj or not photo_obj.photo:
        return None

    storage = photo_obj.photo.storage
    thumb_rel_path = f"photos/thumbs/{photo_obj.id}_{size}.jpg"
    if storage.exists(thumb_rel_path):
        return storage.url(thumb_rel_path)

    try:
        photo_obj.photo.open()
        with Image.open(photo_obj.photo) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70, optimize=True)
        buffer.seek(0)
        storage.save(thumb_rel_path, ContentFile(buffer.getvalue()))
        return storage.url(thumb_rel_path)
    except Exception:
        return photo_obj.photo.url


def _build_map_mapui_context(request):
    visible_projects = user_projects_qs(request.user)
    base_records = (
        WorkRecord.objects
        .filter(Q(project__in=visible_projects) | Q(project__isnull=True))
        .select_related("project")
    )
    records = list(base_records.order_by("-id"))
    coords_qs = (
        base_records
        .filter(latitude__isnull=False, longitude__isnull=False)
        .annotate(
            photo_count=Count("photos", distinct=True),
            has_any_assessment=Exists(
                TreeAssessment.objects.filter(work_record=OuterRef("pk"))
            ),
        )
        .order_by("-id")
    )
    projects = visible_projects.order_by("name")
    projects_js = list(projects.values("id", "name"))
    coords = []
    for r in coords_qs:
        coords.append({
            "id": r.id,
            "title": r.title or "",
            "external_tree_id": r.external_tree_id or "",
            "taxon": r.taxon or "",
            "project": r.project.name if r.project else "",
            "project_id": r.project_id,
            "lat": r.latitude,
            "lon": r.longitude,
            "has_assessment": bool(getattr(r, "has_any_assessment", False)),
            "has_photos": bool(getattr(r, "photo_count", 0)),
        })

    records_for_select = [
        {
            "id": r.id,
            "title": (r.title or ""),
            "taxon": r.taxon or "",
            "external_tree_id": r.external_tree_id or "",
            "project_id": r.project_id,
            "has_coords": (r.latitude is not None and r.longitude is not None),
        }
        for r in records
    ]

    intervention_form = TreeInterventionForm()
    intervention_note_data_json = mark_safe(
        json.dumps(intervention_form.intervention_type_note_data)
    )

    return {
        "mapy_key": settings.MAPY_API_KEY,
        "projects": projects,
        "projects_js": projects_js,
        "work_records": records,
        "records_with_coords": coords,
        "records_for_select": records_for_select,
        "intervention_form": intervention_form,
        "intervention_note_data_json": intervention_note_data_json,
    }


@login_required
def map_leaflet_test(request):
    target = reverse("map_gl_pilot")
    query = request.META.get("QUERY_STRING")
    if query:
        return redirect(f"{target}?{query}")
    return redirect(target)


@login_required
def workrecords_geojson(request):
    """
    GeoJSON feed with coordinates of WorkRecords (pilot usage for MapLibre map).
    """
    project_param = request.GET.get("project")
    if project_param:
        try:
            project_id = int(project_param)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid project parameter")
        project = get_object_or_404(Project, pk=project_id)
        if not user_can_view_project(request.user, project.pk):
            return JsonResponse({"error": "Forbidden"}, status=403)
        qs = project.trees.filter(
            latitude__isnull=False,
            longitude__isnull=False,
        ).only("id", "latitude", "longitude", "external_tree_id", "title")
    else:
        # Use the Project.trees M2M as the source of truth; legacy FK can drift.
        visible_projects = user_projects_qs(request.user)
        qs = (
            WorkRecord.objects.filter(
                Q(projects__in=visible_projects),
                latitude__isnull=False,
                longitude__isnull=False,
            )
            .distinct()
            .only("id", "latitude", "longitude", "external_tree_id", "title")
        )

    # TODO: this pilot endpoint will be replaced by the registry-driven map feed later.
    bbox_param = request.GET.get("bbox")
    if bbox_param:
        try:
            min_lon, min_lat, max_lon, max_lat = [float(part) for part in bbox_param.split(",")]
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid bbox parameter"}, status=400)
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon
        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        qs = qs.filter(
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__gte=min_lat,
            latitude__lte=max_lat,
        )

    features = []
    for wr in qs:
        if wr.external_tree_id:
            label = wr.external_tree_id
        elif wr.title:
            label = wr.title
        else:
            label = wr.generate_internal_code() or f"WR {wr.id}"

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [wr.longitude, wr.latitude],
                },
                "properties": {
                    "id": wr.id,
                    "label": label,
                },
            }
        )

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "features": features,
        },
        safe=False,
    )


@login_required
def map_gl_pilot(request):
    """Temporary pilot page to verify MapLibre GL rendering."""
    context = _build_map_mapui_context(request)
    return render(request, "tracker/map_gl_pilot.html", context)


@login_required
def map_project_redirect(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not user_can_view_project(request.user, project.pk):
        return redirect("work_record_list")

    coords_qs = project.trees.filter(
        latitude__isnull=False,
        longitude__isnull=False,
    )
    coords_count = coords_qs.count()
    base_params = {"project": project.pk}
    if coords_count == 0:
        messages.warning(request, "Projekt nemá žádné stromy se souřadnicemi.")
        target = f"{reverse('map_gl_pilot')}?{urlencode(base_params)}"
        return redirect(target)
    if coords_count == 1:
        single = coords_qs.values("latitude", "longitude").first()
        if single:
            lat = single["latitude"]
            lon = single["longitude"]
            params = {"lat": lat, "lon": lon, "z": 18, **base_params}
            return redirect(f"{reverse('map_gl_pilot')}?{urlencode(params)}")

    coords = coords_qs.aggregate(
        min_lat=Min("latitude"),
        max_lat=Max("latitude"),
        min_lon=Min("longitude"),
        max_lon=Max("longitude"),
    )

    target = reverse("map_gl_pilot")
    if all(value is not None for value in coords.values()):
        bbox = f"{coords['min_lon']},{coords['min_lat']},{coords['max_lon']},{coords['max_lat']}"
        params = {"bbox": bbox, **base_params}
        return redirect(f"{target}?{urlencode(params)}")
    return redirect(f"{target}?{urlencode(base_params)}")


@login_required
@require_http_methods(["POST"])
def project_tree_add(request, project_pk, workrecord_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not user_is_foreman(request.user, project.pk):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    work_record = get_object_or_404(WorkRecord, pk=workrecord_pk)
    project.trees.add(work_record)
    if work_record.project_id is None:
        work_record.project = project
        work_record.save(update_fields=["project"])
    return JsonResponse({"ok": True})


@login_required
def pmtiles_range_serve(request, path):
    """
    Serve PMTiles with HTTP Range support for MapLibre/pmtiles.js.
    """
    static_path = finders.find(f"tiles/{path}")
    if not static_path or not os.path.isfile(static_path):
        return HttpResponse(status=404)

    file_size = os.path.getsize(static_path)
    range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
    content_type = "application/octet-stream"

    if range_header and range_header.startswith("bytes="):
        try:
            range_value = range_header.split("=", 1)[1]
            start_str, end_str = (range_value.split("-", 1) + [""])[:2]
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except (ValueError, IndexError):
            return HttpResponse(status=416)

        if start < 0 or end < start or end >= file_size:
            return HttpResponse(status=416)

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
        resp["Content-Length"] = str(end - start + 1)
        resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        resp["Accept-Ranges"] = "bytes"
        return resp

    # Full response
    response = FileResponse(open(static_path, "rb"), content_type=content_type)
    response["Content-Length"] = str(file_size)
    response["Accept-Ranges"] = "bytes"
    return response


@login_required
@require_GET
def workrecord_detail_api(request, pk):
    work_record = (
        WorkRecord.objects
        .filter(pk=pk)
        .select_related("project")
        .prefetch_related(
            Prefetch("photos", queryset=PhotoDocumentation.objects.order_by("-id"))
        )
        .first()
    )
    if not work_record:
        return JsonResponse({"status": "error", "msg": "WorkRecord nenalezen"}, status=404)

    if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
        return JsonResponse({"status": "error", "msg": "Nemáte oprávnění."}, status=403)

    photos = []
    for photo in work_record.photos.all():
        if not photo.photo:
            continue
        full_url = photo.photo.url
        thumb_url = get_photo_thumbnail(photo)
        photos.append({
            "id": photo.id,
            "thumb": thumb_url or full_url,
            "full": full_url,
            "description": photo.description or "",
        })

    has_assessment = work_record.assessments.exists()

    return JsonResponse({
        "status": "ok",
        "record": {
            "id": work_record.id,
            "title": work_record.title or "",
            "external_tree_id": work_record.external_tree_id or "",
            "taxon": work_record.taxon or "",
            "project": work_record.project.name if work_record.project else "",
            "project_id": work_record.project_id,
            "lat": work_record.latitude,
            "lon": work_record.longitude,
            "has_assessment": has_assessment,
            "has_photos": bool(photos),
            "photos": photos,
        },
    })

@login_required
@require_GET
def gbif_taxon_suggest(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    qs = (
        Species.objects
        .filter(Q(latin_name__icontains=q) | Q(czech_name__icontains=q))
        .order_by("latin_name")[:20]
    )

    results = []
    for sp in qs:
        latin = sp.latin_name
        czech = sp.czech_name or ""
        if czech:
            display = f"{czech} ({latin})"
        else:
            display = latin

        results.append(
            {
                "gbif_key": None,
                "scientific_name": latin,
                "vernacular_name": czech,
                "display": display,
            }
        )

    return JsonResponse({"results": results})

@login_required
def save_coordinates(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=405)

    record_id = request.POST.get("record_id")
    lat_str = request.POST.get("latitude")
    lon_str = request.POST.get("longitude")

    try:
        record = WorkRecord.objects.get(id=record_id)
    except WorkRecord.DoesNotExist:
        return JsonResponse({"status": "error", "msg": "Record not found"}, status=404)

    if record.project_id and not user_can_view_project(request.user, record.project_id):
        return JsonResponse({"status": "error", "msg": "Forbidden"}, status=403)

    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "msg": "Invalid coordinates"}, status=400)

    record.latitude = lat
    record.longitude = lon
    record.save(update_fields=["latitude", "longitude"])
    return JsonResponse({"status": "ok"})


@login_required
def map_upload_photo(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=405)

    record_id = request.POST.get("record_id")
    comment = request.POST.get("comment", "").strip()
    photo_file = request.FILES.get("photo")

    if not record_id or not photo_file:
        return JsonResponse({"status": "error", "msg": "Chybí data"}, status=400)

    try:
        record = WorkRecord.objects.get(id=record_id)
    except WorkRecord.DoesNotExist:
        return JsonResponse({"status": "error", "msg": "Úkon nenalezen"}, status=404)

    if record.project_id and not user_can_view_project(request.user, record.project_id):
        return JsonResponse({"status": "error", "msg": "Nemáš oprávnění"}, status=403)

    photo_doc = PhotoDocumentation.objects.create(
        work_record=record,
        photo=photo_file,
        description=comment
    )

    thumb_url = get_photo_thumbnail(photo_doc)
    return JsonResponse({
        "status": "ok",
        "photo": {
            "id": photo_doc.id,
            "thumb": thumb_url or (photo_doc.photo.url if photo_doc.photo else ""),
            "full": photo_doc.photo.url if photo_doc.photo else "",
            "description": comment,
        }
    })


@login_required
def map_create_work_record(request):
    """
    Vytvoří nový úkon přímo z mapy (AJAX, bez přesměrování).
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=405)

    external_tree_id = (request.POST.get("title") or "").strip()
    taxon_value = (request.POST.get("taxon") or "").strip()
    taxon_czech_value = (request.POST.get("taxon_czech") or "").strip()
    taxon_latin_value = (request.POST.get("taxon_latin") or "").strip()
    gbif_key_raw = (request.POST.get("taxon_gbif_key") or "").strip()
    project_id = request.POST.get("project_id") or request.POST.get("project") or request.GET.get("project") or None
    date_str = (request.POST.get("date") or "").strip()
    lat_str = request.POST.get("latitude")
    lon_str = request.POST.get("longitude")

    # souřadnice jsou pro mapu povinné
    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "msg": "Chybné souřadnice."}, status=400)

    # projekt (volitelný)
    project = None
    if project_id and project_id != "none":
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return JsonResponse({"status": "error", "msg": "Projekt nenalezen."}, status=404)
        if not user_can_view_project(request.user, project.pk):
            return JsonResponse({"status": "error", "msg": "Nemáš oprávnění."}, status=403)

    # datum – pokud nepřijde, použijeme dnešek
    from django.utils import timezone

    if date_str:
        parsed = parse_date(date_str)
        record_date = parsed or timezone.localdate()
    else:
        record_date = timezone.localdate()

    taxon_gbif_key = None
    if gbif_key_raw:
        try:
            taxon_gbif_key = int(gbif_key_raw)
        except ValueError:
            taxon_gbif_key = None

    work_record = WorkRecord(
        project=project,
        external_tree_id=external_tree_id or None,
        taxon=taxon_value or "",
        taxon_czech=taxon_czech_value,
        taxon_latin=taxon_latin_value,
        taxon_gbif_key=taxon_gbif_key,
        latitude=lat,
        longitude=lon,
        date=record_date,
    )
    work_record.save()
    work_record.sync_title_from_identifiers()
    work_record.save(
        update_fields=[
            "title",
            "external_tree_id",
            "taxon",
            "taxon_czech",
            "taxon_latin",
            "taxon_gbif_key",
            "project",
            "latitude",
            "longitude",
            "date",
        ]
    )

    if project:
        project.trees.add(work_record)
        if settings.DEBUG:
            print(f"[map_create_work_record] project_id={project.pk} work_record_id={work_record.pk}")

    return JsonResponse({
        "status": "ok",
        "record": {
            "id": work_record.id,
            "title": work_record.title or "",
            "external_tree_id": work_record.external_tree_id or "",
            "taxon": work_record.taxon or "",
            "taxon_czech": work_record.taxon_czech or "",
            "taxon_latin": work_record.taxon_latin or "",
            "taxon_gbif_key": work_record.taxon_gbif_key,
            "project": work_record.project.name if work_record.project else "",
            "project_id": work_record.project_id,
            "lat": work_record.latitude,
            "lon": work_record.longitude,
        },
    })


@login_required
@require_http_methods(["GET", "POST"])
def workrecord_assessment_api(request, pk):
    """
    JSON API for reading TreeAssessments tied to a WorkRecord.
    GET: return the latest assessment values (or nulls if none exist).
    POST: append a new assessment version from JSON payload.
    """
    try:
        work_record = WorkRecord.objects.get(pk=pk)
    except WorkRecord.DoesNotExist:
        return JsonResponse({"error": "WorkRecord not found"}, status=404)

    if request.method == "GET":
        assessment = work_record.latest_assessment
        data = {
            "work_record_id": work_record.pk,
            "dbh_cm": assessment.dbh_cm if assessment else None,
            "height_m": assessment.height_m if assessment else None,
            "crown_width_m": str(assessment.crown_width_m) if assessment and assessment.crown_width_m is not None else None,
            "crown_area_m2": str(assessment.crown_area_m2) if assessment and assessment.crown_area_m2 is not None else None,
            "physiological_age": assessment.physiological_age if assessment else None,
            "vitality": assessment.vitality if assessment else None,
            "health_state": assessment.health_state if assessment else None,
            "stability": assessment.stability if assessment else None,
            "perspective": assessment.perspective if assessment else None,
            "assessed_at": assessment.assessed_at.isoformat() if assessment and assessment.assessed_at else None,
        }
        return JsonResponse(data)

    # POST
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    def parse_int(value, min_val, max_val):
        if value in (None, ""):
            return None
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return None
        if iv < min_val or iv > max_val:
            return None
        return iv

    def parse_float(value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def parse_decimal(value):
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    dbh_cm = parse_float(payload.get("dbh_cm"))
    height_m = parse_float(payload.get("height_m"))
    crown_width_m = parse_decimal(payload.get("crown_width_m"))
    physiological_age = parse_int(payload.get("physiological_age"), 1, 5)
    vitality = parse_int(payload.get("vitality"), 1, 5)
    health_state = parse_int(payload.get("health_state"), 1, 5)
    stability = parse_int(payload.get("stability"), 1, 5)
    perspective = payload.get("perspective") or None
    if perspective not in (None, "", "a", "b", "c"):
        perspective = None

    assessment = TreeAssessment.objects.create(
        work_record=work_record,
        assessed_at=date.today(),
        dbh_cm=dbh_cm,
        height_m=height_m,
        crown_width_m=crown_width_m,
        physiological_age=physiological_age,
        vitality=vitality,
        health_state=health_state,
        stability=stability,
        perspective=perspective,
    )

    return JsonResponse({
        "status": "ok",
        "id": assessment.pk,
        "work_record_id": work_record.pk,
        "dbh_cm": assessment.dbh_cm,
        "height_m": assessment.height_m,
        "crown_width_m": str(assessment.crown_width_m) if assessment.crown_width_m is not None else None,
        "crown_area_m2": str(assessment.crown_area_m2) if assessment.crown_area_m2 is not None else None,
        "physiological_age": assessment.physiological_age,
        "vitality": assessment.vitality,
        "health_state": assessment.health_state,
        "stability": assessment.stability,
        "perspective": assessment.perspective,
        "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None,
    })


@login_required
def bulk_handover_interventions(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    if request.method != "POST":
        return redirect("project_detail", pk=pk)

    selected_ids = request.POST.getlist("selected_records")
    if not selected_ids:
        messages.warning(request, "Vyberte prosím alespoň jeden strom / úkon.")
        return redirect("project_detail", pk=pk)

    work_records = project.trees.filter(id__in=selected_ids)
    interventions_qs = TreeIntervention.objects.filter(
        tree__in=work_records,
        status__in=["approved", "in_progress"],
    )
    interventions = list(interventions_qs)

    if not interventions:
        messages.info(request, "Nebyl nalezen žádný zásah vhodný k předání ke kontrole.")
        return redirect("project_detail", pk=pk)

    for intervention in interventions:
        if hasattr(intervention, "mark_handed_over_for_check"):
            intervention.mark_handed_over_for_check()
        else:
            from django.utils import timezone

            intervention.status = "pending_check"
            if getattr(intervention, "handed_over_for_check_at", None) is None:
                intervention.handed_over_for_check_at = timezone.now()
            intervention.save()

    messages.success(
        request,
        f"Předáno ke kontrole {len(interventions)} zásahů.",
    )
    return redirect("project_detail", pk=pk)


@login_required
def bulk_complete_interventions(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    if request.method != "POST":
        return redirect("project_detail", pk=pk)

    selected_ids = request.POST.getlist("selected_records")
    if not selected_ids:
        messages.warning(request, "Vyberte prosím alespoň jeden strom / úkon.")
        return redirect("project_detail", pk=pk)

    work_records = project.trees.filter(id__in=selected_ids)
    interventions_qs = TreeIntervention.objects.filter(
        tree__in=work_records,
        status__in=["pending_check", "approved", "in_progress"],
    )
    interventions = list(interventions_qs)

    if not interventions:
        messages.info(request, "Nebyl nalezen žádný zásah k označení jako dokončený.")
        return redirect("project_detail", pk=pk)

    for intervention in interventions:
        intervention.status = "completed"
        intervention.save()

    messages.success(
        request,
        f"Označeno {len(interventions)} zásahů jako dokončené.",
    )
    return redirect("project_detail", pk=pk)
