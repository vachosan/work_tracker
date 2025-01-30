from django.shortcuts import render, redirect
from .forms import WorkRecordForm, PhotoDocumentationForm
from .models import WorkRecord

def create_work_record(request):
    if request.method == 'POST':
        form = WorkRecordForm(request.POST)
        if form.is_valid():
            work_record = form.save()
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        form = WorkRecordForm()
    return render(request, 'tracker/create_work_record.html', {'form': form})

def work_record_detail(request, pk):
    work_record = WorkRecord.objects.get(pk=pk)
    if request.method == 'POST':
        photo_form = PhotoDocumentationForm(request.POST, request.FILES)
        if photo_form.is_valid():
            photo = photo_form.save(commit=False)
            photo.work_record = work_record
            photo.save()
            return redirect('work_record_detail', pk=work_record.pk)
    else:
        photo_form = PhotoDocumentationForm()
    return render(request, 'tracker/work_record_detail.html', {'work_record': work_record, 'photo_form': photo_form})