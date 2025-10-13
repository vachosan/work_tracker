from django import forms
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model  # místo přímého importu User (viz níže)
from django.utils.dateformat import format

from .models import WorkRecord, PhotoDocumentation, Project, ProjectMembership

# z get_user_model() načteme správný uživatelský model (můžeš mít vlastní User)
User = get_user_model()


# --------------------------------------
# ÚPRAVA / SPRÁVA PROJEKTŮ
# --------------------------------------
class ProjectEditForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'is_closed']


class AddMemberForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(), label="Uživatel")
    role = forms.ChoiceField(choices=ProjectMembership.Role.choices, label="Role")


# --------------------------------------
# REGISTRACE UŽIVATELE
# --------------------------------------
class CustomUserCreationForm(UserCreationForm):
    """Formulář pro vytvoření nového uživatele (registrace)"""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")

    def save(self, commit=True):
        """Uloží uživatele s doplněnými údaji"""
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user


class ProjectForm(forms.ModelForm):
    """Základní formulář pro vytvoření projektu"""
    class Meta:
        model = Project
        fields = ['name', 'description']


# --------------------------------------
# ÚKONY (WorkRecord)
# --------------------------------------
class WorkRecordForm(forms.ModelForm):
    """Formulář pro vytvoření úkonu"""
    # definuj pole date s hodnotou ve správném formátu
    date = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d'  # <- HTML5 date input očekává ISO formát
        ),
        initial=format(timezone.localdate(), 'Y-m-d'),
        input_formats=['%Y-%m-%d']  # <- povolíme správný vstupní formát
    )
    
    # menší textare pro popis, aby nezabíral moc místa a datum
    
    
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Popis (volitelné)'}),
        label='Popis'
    )

    class Meta:
        model = WorkRecord
        fields = ['title', 'description', 'date', 'project']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),  # HTML5 datepicker
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Novinka: předvyplní aktuální datum při načtení formuláře
        if not self.is_bound and 'date' in self.fields:
            self.fields['date'].initial = timezone.localdate()
        # Filtrování jen na aktivní projekty
        self.fields['project'].queryset = Project.objects.filter(is_closed=False)


# --------------------------------------
# FOTODOKUMENTACE
# --------------------------------------
class PhotoDocumentationForm(forms.ModelForm):
    """Formulář pro nahrání fotky"""
    class Meta:
        model = PhotoDocumentation
        fields = ['photo', 'description']
        widgets = {
            # ✅ Přidaný atribut accept='image/*' → mobilní prohlížeč nabídne foťák nebo galerii
            'photo': forms.ClearableFileInput(attrs={'required': False, 'accept': 'image/*'}),
            # menší popis fotky
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Popis fotky (volitelné)'}),
        }

    def clean_photo(self):
        """Fotka je nepovinná – pokud není vybraná, vrátí None"""
        photo = self.cleaned_data.get('photo')
        if not photo:
            return None
        return photo
