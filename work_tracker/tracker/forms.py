from django import forms
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model  # místo přímého importu User (viz níže)
from django.utils.dateformat import format

from .models import (
    WorkRecord,
    PhotoDocumentation,
    Project,
    ProjectMembership,
    TreeIntervention,
    InterventionType,
)

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
    date = forms.DateField(
        widget=forms.DateInput(
            attrs={'type': 'date', 'autocomplete': 'off'},
            format='%Y-%m-%d'
        ),
        initial=format(timezone.localdate(), 'Y-m-d'),
        input_formats=['%Y-%m-%d']
    )

    class Meta:
        model = WorkRecord
        fields = ['external_tree_id', 'taxon', 'date', 'project']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),  # HTML5 datepicker
        }
        labels = {
            'external_tree_id': 'Číslo stromu (externí)',
            'taxon': 'Taxon',
            'date': 'Datum',
            'project': 'Projekt',
        }
        help_texts = {
            'taxon': 'Botanický název stromu (např. Tilia cordata)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ✅ Novinka: předvyplní aktuální datum při načtení formuláře
        if not self.is_bound and 'date' in self.fields:
            self.fields['date'].initial = timezone.localdate()
        if 'external_tree_id' in self.fields:
            self.fields['external_tree_id'].label = 'Číslo stromu'
            self.fields['external_tree_id'].help_text = 'Číslo stromu z papírové inventarizace, cedulek nebo jiného systému.'
        if 'taxon' in self.fields:
            self.fields['taxon'].label = 'Taxon'
            self.fields['taxon'].help_text = 'Botanický název stromu (např. Tilia cordata).'
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
        """Fotka je nepovinná - pokud není vybraná, vrátí None"""
        photo = self.cleaned_data.get('photo')
        if not photo:
            return None
        return photo


class InterventionTypeChoiceField(forms.ModelChoiceField):
    """Výběr typu zásahu se zobrazením kódu a názvu."""

    def label_from_instance(self, obj):
        code = obj.code or ""
        name = obj.name or ""
        if code and name:
            return f"{code} – {name}"
        return name or code or str(obj)


class TreeInterventionForm(forms.ModelForm):
    """Formulář pro zásahy"""
    intervention_type = InterventionTypeChoiceField(
        queryset=InterventionType.objects.none(),
        label="Typ zásahu",
        empty_label="Vyberte typ zásahu",
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Termín zásahu",
    )

    class Meta:
        model = TreeIntervention
        fields = [
            'intervention_type',
            'description',
            'urgency',
            'status',
            'due_date',
            'assigned_to',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Popis zásahu (volitelný)'}),
        }
        labels = {
            'description': 'Popis zásahu / poznámka',
            'urgency': 'Naléhavost',
            'status': 'Stav zásahu',
            'assigned_to': 'Zodpovědný',
        }
        help_texts = {
            'assigned_to': 'Volitelně vyber osobu, která bude zásah řešit.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = InterventionType.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['intervention_type'].queryset = queryset
        self.fields['assigned_to'].queryset = User.objects.filter(is_active=True).order_by('username')

    @property
    def intervention_type_note_data(self):
        data = {}
        queryset = self.fields['intervention_type'].queryset
        for item in queryset:
            data[str(item.pk)] = {
                "note_required": bool(item.note_required),
                "note_hint": item.note_hint or "",
            }
        return data
