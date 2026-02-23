from django.contrib import admin
from .models import (
    WorkRecord,
    PhotoDocumentation,
    Project,
    ProjectMembership,
    TreeAssessment,
    InterventionType,
    TreeIntervention,
    Dataset,
    DatasetTree,
    ProjectTree,
)

# ---------- Inlines ----------

class PhotoDocumentationInline(admin.TabularInline):
    model = PhotoDocumentation
    extra = 1
    fields = ("photo", "description")
    show_change_link = True


class TreeAssessmentInline(admin.StackedInline):
    model = TreeAssessment
    extra = 1
    fields = (
        "assessed_at",
        "dbh_cm",
        "stem_circumference_cm",
        "stem_diameters_cm_list",
        "stem_circumferences_cm_list",
        "height_m",
        "crown_width_m",
        "crown_area_m2",
        "physiological_age",
        "vitality",
        "health_state",
        "stability",
        "mistletoe_level",
        "perspective",
        "access_obstacle_level",
    )

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
    list_display = ("title", "external_tree_id", "taxon", "project", "date", "latitude", "longitude")
    list_filter = ("project", "date", "latitude", "longitude")
    search_fields = ("title", "external_tree_id", "taxon")
    date_hierarchy = "date"
    autocomplete_fields = ("project",)
    inlines = [PhotoDocumentationInline, TreeAssessmentInline]

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


@admin.register(InterventionType)
class InterventionTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "is_selectable", "order")
    list_filter = ("is_active", "is_selectable")
    ordering = ("order", "name")


@admin.register(TreeIntervention)
class TreeInterventionAdmin(admin.ModelAdmin):
    list_display = ("tree", "intervention_type", "urgency_label", "status", "due_date")
    list_filter = ("status", "urgency", "intervention_type")
    search_fields = ("tree__title", "tree__external_tree_id", "description")

    def urgency_label(self, obj):
        return obj.get_urgency_display()

    urgency_label.short_description = "Naléhavost"


@admin.register(TreeAssessment)
class TreeAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "work_record",
        "assessed_at",
        "access_obstacle_level",
        "access_obstacle_label",
    )
    list_filter = ("assessed_at", "access_obstacle_level")
    search_fields = ("work_record__title", "work_record__external_tree_id")

    def access_obstacle_label(self, obj):
        return obj.get_access_obstacle_label()

    access_obstacle_label.short_description = "Překážky"


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "visibility", "is_system", "allow_public_observations", "created_at")
    list_filter = ("visibility", "is_system", "allow_public_observations")
    search_fields = ("name",)


@admin.register(DatasetTree)
class DatasetTreeAdmin(admin.ModelAdmin):
    list_display = ("dataset", "tree")
    list_filter = ("dataset",)
    search_fields = ("dataset__name", "tree__title")


@admin.register(ProjectTree)
class ProjectTreeAdmin(admin.ModelAdmin):
    list_display = ("project", "tree", "added_by", "added_at")
    list_filter = ("project",)
    search_fields = ("project__name", "tree__title")
