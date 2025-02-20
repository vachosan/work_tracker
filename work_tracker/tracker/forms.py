from django import forms
from .models import WorkRecord, PhotoDocumentation, Project
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        
class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = ['title', 'description', 'date', 'project']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("Filtruji projekty: pouze aktivní")
        self.fields['project'].queryset = Project.objects.filter(is_closed=False)  # Pouze aktivní projekty

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