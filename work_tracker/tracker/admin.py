from django.contrib import admin
from .models import WorkRecord, PhotoDocumentation, Project

#admin.site.register(WorkRecord)
admin.site.register(PhotoDocumentation)
# Register your models here.
@admin.register(WorkRecord)
class WorkRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'description']  # Zobrazovaná pole v seznamu
    list_filter = ['date']  # Filtrování podle data
    search_fields = ['title', 'description']  # Vyhledávání podle názvu a popisu

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_closed')  # Zobrazí sloupec "is_closed" v seznamu projektů
    list_filter = ('is_closed',)  # Přidá filtr pro uzavřené/otevřené projekty
    search_fields = ('name',)  # Umožní vyhledávání podle názvu projektu