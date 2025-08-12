import os
from django.conf import settings
from django.core.files import File
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from .models import Project, WorkRecord, PhotoDocumentation, ProjectMembership
from .forms import ProjectEditForm, AddMemberForm
from .models import ProjectMembership
from django.db.models import Max, F
from .forms import (
    WorkRecordForm,
    PhotoDocumentationForm,
    ProjectForm,
    CustomUserCreationForm,
)
from .models import WorkRecord, PhotoDocumentation, Project
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
def edit_project(request, pk):
    project = get_object_or_404(Project, pk=pk)

    # Jen stavbyvedoucí
    from .models import ProjectMembership
    membership = ProjectMembership.objects.filter(user=request.user, project=project, role=ProjectMembership.Role.FOREMAN).first()
    if not membership:
        return redirect('work_record_list')

    # Formuláře
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

    # Jen stavbyvedoucí
    membership = ProjectMembership.objects.filter(user=request.user, project=project, role=ProjectMembership.Role.FOREMAN).first()
    if not membership:
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

            # >>> přidej autora jako STAVBYVEDOUCÍHO (FOREMAN)
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
    if not ProjectMembership.objects.filter(user=request.user, project=project, role=ProjectMembership.Role.FOREMAN).exists():
        return redirect('work_record_list')
    project.is_closed = True
    project.save()
    return redirect('work_record_list')

@login_required
def activate_project(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not ProjectMembership.objects.filter(user=request.user, project=project, role=ProjectMembership.Role.FOREMAN).exists():
        return redirect('work_record_list')
    project.is_closed = False
    project.save()
    return redirect('closed_projects_list')  # po otevření se vrať na „uzavřené“, ať je to přehledné

@login_required
def closed_projects_list(request):
    projects = (
        user_projects_qs(request.user)
        .filter(is_closed=True)
        .annotate(latest_work_time=Max('work_records__created_at'))
        .order_by(F('latest_work_time').desc(nulls_last=True), '-id')
    )
    for p in projects:
        p.is_foreman = ProjectMembership.objects.filter(
            user=request.user, project=p, role=ProjectMembership.Role.FOREMAN
        ).exists()
    return render(request, 'tracker/closed_projects_list.html', {'projects': projects})

# ------------------ WorkRecord ------------------

@login_required
def work_record_list(request):
    # projekty, kde je uživatel členem
    projects = (
        user_projects_qs(request.user)
        .filter(is_closed=False) # pouze aktivní projekty
        .annotate(
            latest_work_time=Max('work_records__created_at')  # poslední úkon v projektu
        )
        .order_by(F('latest_work_time').desc(nulls_last=True), '-id')  # nejnovější nahoře, prázdné projekty nakonec
        .prefetch_related('work_records')
    )

    # flag pro tlačítko "Editovat projekt" (jen pro FOREMAN)
    for p in projects:
        p.is_foreman = ProjectMembership.objects.filter(
            user=request.user, project=p, role=ProjectMembership.Role.FOREMAN
        ).exists()

    work_records_without_project = WorkRecord.objects.filter(project__isnull=True)

    return render(request, 'tracker/work_record_list.html', {
        'projects': projects,
        'work_records_without_project': work_records_without_project,
    })
@login_required
def create_work_record(request, project_id=None):
    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        if work_record_form.is_valid():
            work_record = work_record_form.save()

            # po uložení ověřit, že má user přístup k projektu (pokud je vybraný)
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
            # zajistí 404, pokud user nemá přístup
            project = get_project_or_404_for_user(request.user, project_id)
            initial_data['project'] = project

        work_record_form = WorkRecordForm(initial=initial_data)
        photo_form = PhotoDocumentationForm()

    return render(request, 'tracker/create_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
    })

@login_required
def work_record_detail(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)

    # přístup jen pro členy projektu
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
                work_record_form.save()
                return redirect('work_record_detail', pk=work_record.pk)

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

    # přístup jen pro členy projektu
    if work_record.project_id and not user_can_view_project(request.user, work_record.project_id):
        return redirect('work_record_list')

    if request.method == "POST":
        form = PhotoDocumentationForm(request.POST, request.FILES)
        photo = request.FILES.get("photo")

        if not photo:
            # použij default z MEDIA_ROOT/photos/default.jpg
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
    # přístup jen pro členy projektu
    if photo.work_record.project_id and not user_can_view_project(request.user, photo.work_record.project_id):
        return redirect('work_record_list')
    work_record_pk = photo.work_record.pk
    photo.delete()
    return redirect('edit_work_record', pk=work_record_pk)
