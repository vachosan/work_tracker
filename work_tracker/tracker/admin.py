from django.contrib import admin
from .models import WorkRecord, PhotoDocumentation

#admin.site.register(WorkRecord)
admin.site.register(PhotoDocumentation)
# Register your models here.
@admin.register(WorkRecord)
class WorkRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'description']  # Zobrazovaná pole v seznamu
    list_filter = ['date']  # Filtrování podle data
    search_fields = ['title', 'description']  # Vyhledávání podle názvu a popisu