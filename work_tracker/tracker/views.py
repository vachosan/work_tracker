from django.shortcuts import render, redirect
from .forms import WorkRecordForm, PhotoDocumentationForm
from .models import WorkRecord
from django.shortcuts import get_object_or_404
from django.urls import reverse

def create_work_record(request):
    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST)
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)

        if work_record_form.is_valid() and photo_form.is_valid():
            # Uložení pracovního úkonu
            work_record = work_record_form.save()

            # Uložení fotografie s odkazem na pracovní úkon
            photo = photo_form.save(commit=False)
            photo.work_record = work_record
            photo.save()

            return redirect('work_record_detail', pk=work_record.pk)
    else:
        work_record_form = WorkRecordForm()
        photo_form = PhotoDocumentationForm()

    return render(request, 'tracker/create_work_record.html', {
        'work_record_form': work_record_form,
        'photo_form': photo_form,
    })

def work_record_detail(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)
    return render(request, 'tracker/work_record_detail.html', {
        'work_record': work_record,
    })

def edit_work_record(request, pk):
    work_record = get_object_or_404(WorkRecord, pk=pk)

    if request.method == 'POST':
        work_record_form = WorkRecordForm(request.POST, instance=work_record)
        if work_record_form.is_valid():
            work_record_form.save()
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        work_record_form = WorkRecordForm(instance=work_record)

    return render(request, 'tracker/edit_work_record.html', {
        'work_record_form': work_record_form,
    })

def work_record_list(request):
    work_records = WorkRecord.objects.all()
    return render(request, 'tracker/work_record_list.html', {
        'work_records': work_records,
    })