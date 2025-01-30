from django import forms
from .models import WorkRecord, PhotoDocumentation

class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = ['title', 'description', 'start_time', 'end_time', 'note']

class PhotoDocumentationForm(forms.ModelForm):
    class Meta:
        model = PhotoDocumentation
        fields = ['photo', 'description']