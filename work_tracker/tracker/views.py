import os
import io
import zipfile
import unicodedata
import re
import tempfile
import zipstream
from django.contrib import messages
from django.http import StreamingHttpResponse
from django.http import FileResponse
from datetime import date
from django.conf import settings
from django.core.files import File
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Max, F
from django.urls import reverse
from django.db.models import Max, F, Count, Q
from django.db.models import Prefetch
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from .models import WorkRecord, Project
from django.http import JsonResponse
from .models import Project, WorkRecord, PhotoDocumentation, ProjectMembership
from .forms import (
    WorkRecordForm,
    PhotoDocumentationForm,
    ProjectForm,
    CustomUserCreationForm,
    ProjectEditForm,
    AddMemberForm,
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

    qs = WorkRecord.objects.filter(project=project).order_by('-created_at')

    # filtry (GET)
    q = request.GET.get('q', '').strip()
    df = parse_date(request.GET.get('date_from') or '')
    dt = parse_date(request.GET.get('date_to') or '')

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if df:
        qs = qs.filter(date__gte=df)
    if dt:
        qs = qs.filter(date__lte=dt)

    # stránkování
    paginator = Paginator(qs, 20)  # 20 na stránku
    page_obj = paginator.get_page(request.GET.get('page'))

    # flag pro tlačítka
    is_foreman = ProjectMembership.objects.filter(
        user=request.user, project=project, role=ProjectMembership.Role.FOREMAN
    ).exists()

    return render(request, 'tracker/project_detail.html', {
        'project': project,
        'page_obj': page_obj,
        'q': q,
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'is_foreman': is_foreman,
    })

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
            wr_count=Count('work_records')
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
    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        if work_record_form.is_valid():
            work_record = work_record_form.save()

            # Set coordinates if provided (from map)
            lat_str = request.POST.get("latitude") or request.GET.get("lat")
            lon_str = request.POST.get("longitude") or request.GET.get("lon")
            try:
                if lat_str is not None and lon_str is not None:
                    work_record.latitude = float(lat_str)
                    work_record.longitude = float(lon_str)
                    work_record.save(update_fields=["latitude", "longitude"]) 
            except (TypeError, ValueError):
                pass

            # ověř přístup k projektu
            if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
                return redirect('work_record_list')

            if 'photo' in request.FILES and photo_form.is_valid():
                photo = photo_form.save(commit=False)
                photo.work_record = work_record
                photo.save()

            return redirect('work_record_detail', pk=work_record.pk)
    else:
        initial_data = {}
        if project_id:
            project = get_project_or_404_for_user(request.user, project_id)
            initial_data['project'] = project

        work_record_form = WorkRecordForm(initial=initial_data)
        photo_form = PhotoDocumentationForm()

    return render(request, 'tracker/create_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
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
    work_record = get_object_or_404(WorkRecord, pk=pk)

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

    return render(request, 'tracker/work_record_detail.html', {
        'work_record': work_record,
        'photo_form': photo_form,
        'photos': valid_photos,
    })


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
                work_record = work_record_form.save()
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

@login_required
def export_selected_zip(request, pk):
    """Export vybraných nebo všech úkonů projektu jako streamovaný ZIP (nízká paměťová náročnost)."""
    project = get_object_or_404(Project, pk=pk)

    if not user_can_view_project(request.user, project.pk):
        return redirect('work_record_list')

    # vybrané nebo všechny úkony
    if "export_all" in request.POST:
        work_records = WorkRecord.objects.filter(project=project)
    else:
        selected_ids = request.POST.getlist("selected_records")
        if not selected_ids:
            return redirect("project_detail", pk=pk)
        work_records = WorkRecord.objects.filter(id__in=selected_ids, project=project)

    # helper na čisté názvy
    def slugify_folder(name):
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
        name = re.sub(r'[^a-zA-Z0-9_-]+', '_', name)
        return name.strip('_') or 'ukon'

    # vytvoření streamovacího ZIP objektu
    z = zipstream.ZipFile(mode='w', compression=zipfile.ZIP_DEFLATED)

    for record in work_records:
        folder = slugify_folder(record.title or f"ukon_{record.id}")
        photos = PhotoDocumentation.objects.filter(work_record=record)

        for photo in photos:
            if photo.photo and os.path.exists(photo.photo.path):
                base_filename = os.path.basename(photo.photo.name)
                ext = os.path.splitext(base_filename)[1] or ".jpg"

                if photo.description:
                    safe_name = slugify_folder(photo.description)
                    filename = f"{safe_name}{ext}"
                else:
                    filename = base_filename

                arcname = os.path.join(folder, filename)
                z.write(photo.photo.path, arcname)

    # příprava odpovědi
    today_str = date.today().strftime("%Y-%m-%d")
    filename = f'{slugify_folder(project.name)}_{today_str}.zip'

    response = StreamingHttpResponse(z, content_type='application/zip')
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
@login_required
def map_leaflet_test(request):
    visible_projects = user_projects_qs(request.user)
    records = (
        WorkRecord.objects
        .filter(Q(project__in=visible_projects) | Q(project__isnull=True))
        .order_by("-id")[:50]
    )
    projects = visible_projects.order_by("name")
    projects_js = list(projects.values("id", "name"))
    coords = [
        {
            "id": r.id,
            "title": r.title or "(bez názvu)",
            "description": r.description or "",
            "project": r.project.name if r.project else "",
            "project_id": r.project_id,
            "lat": r.latitude,
            "lon": r.longitude,
        }
        for r in records if r.latitude and r.longitude
    ]

    records_for_select = [
        {
            "id": r.id,
            "title": (r.title or ""),
            "project_id": r.project_id,
            "has_coords": bool(r.latitude and r.longitude),
        }
        for r in records
    ]

    context = {
        "mapy_key": settings.MAPY_API_KEY,
        "projects": projects,
        "projects_js": projects_js,
        "work_records": records,
        "records_with_coords": coords,
        "records_for_select": records_for_select,
    }
    return render(request, "tracker/map_leaflet.html", context)

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
