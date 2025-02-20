from django import forms
from .models import WorkRecord, PhotoDocumentation, Project

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        
class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = ['title', 'description', 'date', 'project']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),  # Použij HTML5 date picker
        }
class PhotoDocumentationForm(forms.ModelForm):
    class Meta:
        model = PhotoDocumentation
        fields = ['photo', 'description']
        widgets = {
            'photo': forms.ClearableFileInput(attrs={'required': False}),  # Fotka je volitelná
        }
        
    def clean_photo(self):
        # Pokud není nahraná fotka, pole není povinné
        photo = self.cleaned_data.get('photo')
        if not photo:
            return None
        return photo