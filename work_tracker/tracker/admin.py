from django.contrib import admin
from .models import WorkRecord, PhotoDocumentation, Project, ProjectMembership

# ---------- Inlines ----------

class PhotoDocumentationInline(admin.TabularInline):
    model = PhotoDocumentation
    extra = 1
    fields = ("photo", "description")
    show_change_link = True

class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 1
    autocomplete_fields = ("user",)
    fields = ("user", "role")

# ---------- Project ----------

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_closed")
    list_filter = ("is_closed",)
    search_fields = ("name", "description")
    inlines = [ProjectMembershipInline]
    # Volitelné: aby šel projekt vybírat v jiných adminech přes autocomplete
    # ať to ale dává smysl jen pokud je projektů hodně
    # autocomplete_fields = ()

# ---------- WorkRecord ----------

@admin.register(WorkRecord)
class WorkRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "date")
    list_filter = ("project", "date")
    search_fields = ("title", "description")
    date_hierarchy = "date"
    autocomplete_fields = ("project",)
    inlines = [PhotoDocumentationInline]

# ---------- PhotoDocumentation ----------

@admin.register(PhotoDocumentation)
class PhotoDocumentationAdmin(admin.ModelAdmin):
    list_display = ("id", "work_record", "description")
    list_filter = ("work_record__project",)
    search_fields = ("description", "work_record__title")
    autocomplete_fields = ("work_record",)

# ---------- ProjectMembership ----------

@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "role")
    list_filter = ("role", "project")
    search_fields = ("user__username", "user__email", "project__name")
    autocomplete_fields = ("user", "project")
