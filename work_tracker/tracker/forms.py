from django import forms
from .models import WorkRecord, PhotoDocumentation

class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = ['title', 'description', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),  # Použij HTML5 date picker
        }
class PhotoDocumentationForm(forms.ModelForm):
    class Meta:
        model = PhotoDocumentation
        fields = ['photo', 'description']