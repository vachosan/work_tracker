from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .forms import WorkRecordForm, PhotoDocumentationForm, ProjectForm
from .models import WorkRecord, PhotoDocumentation, Project

def create_project(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.is_closed = False  # Nový projekt je automaticky aktivní
            project.save()
            return redirect('work_record_list')
    else:
        form = ProjectForm()
    return render(request, 'tracker/create_project.html', {'form': form})



def create_work_record(request, project_id=None):
    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        if work_record_form.is_valid():
            work_record = work_record_form.save()

            if 'photo' in request.FILES:
                photo = photo_form.save(commit=False)
                photo.work_record = work_record
                photo.save()

            return redirect('work_record_detail', pk=work_record.pk)
    else:
        initial_data = {}
        if project_id:
            project = Project.objects.get(pk=project_id)
            initial_data['project'] = project  # Předvyplní projekt

        work_record_form = WorkRecordForm(initial=initial_data)
        photo_form = PhotoDocumentationForm()

    return render(request, 'tracker/create_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
    })

def work_record_detail(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)

    if request.method == 'POST':
        # Zpracování formuláře pro přidání fotky
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)
        if photo_form.is_valid():
            photo = photo_form.save(commit=False)
            photo.work_record = work_record
            photo.save()
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        photo_form = PhotoDocumentationForm()

    # Načtení všech fotografií pro daný úkon
    photos = work_record.photos.all()

    # Filtrování fotografií, které mají přiřazený soubor
    valid_photos = [photo for photo in photos if photo.photo]

    return render(request, 'tracker/work_record_detail.html', {
        'work_record': work_record,
        'photo_form': photo_form,
        'photos': valid_photos,
    })

def edit_work_record(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)

    if request.method == 'POST':
        # Zpracování formuláře pro úpravu úkonu
        work_record_form = WorkRecordForm(request.POST, instance=work_record)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        # Uložení úkonu
        if 'save_work_record' in request.POST and work_record_form.is_valid():
            work_record_form.save()

            return redirect('work_record_detail', pk=work_record.pk)

        # Pokud je přítomen soubor, přidáme fotku
        if 'add_photo' in request.POST and photo_form.is_valid():
            if 'photo' in request.FILES:  # Zkontrolujeme, zda je soubor přítomen
                photo = photo_form.save(commit=False)
                photo.work_record = work_record
                photo.save()
                return redirect('edit_work_record', pk=work_record.pk)

    else:
        work_record_form = WorkRecordForm(instance=work_record)
        photo_form = PhotoDocumentationForm()

    # Načtení všech fotografií pro daný úkon
    photos = work_record.photos.all()

    return render(request, 'tracker/edit_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
        'photos': photos,
        'work_record': work_record,
    })

def work_record_list(request):
    projects = Project.objects.prefetch_related('work_records').all()
    work_records_without_project = WorkRecord.objects.filter(project__isnull=True)  # Úkony bez projektu

    return render(request, 'tracker/work_record_list.html', {
        'projects': projects,
        'work_records_without_project': work_records_without_project,
    })
#def work_record_list(request):
 #    projects = Project.objects.prefetch_related('work_records').all()
    #work_records = WorkRecord.objects.all()
  #  return render(request, 'tracker/work_record_list.html', {
   #     'work_records': work_records,
    #})

def delete_photo(request, pk):
    photo = get_object_or_404(PhotoDocumentation, pk=pk)
    work_record_pk = photo.work_record.pk
    photo.delete()
    return redirect('edit_work_record', pk=work_record_pk)

def close_project(request, pk):
    project = get_object_or_404(Project, pk=pk)
    project.is_closed = True
    project.save()
    return redirect('work_record_list')

def activate_project(request, pk):
    project = get_object_or_404(Project, pk=pk)
    project.is_closed = False  # Nastaví projekt jako aktivní
    project.save()
    return redirect('work_record_list')