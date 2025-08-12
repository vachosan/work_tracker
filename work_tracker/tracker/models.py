from django.db import models
from django.utils import timezone
from django.conf import settings


class Project(models.Model):
    name = models.CharField(max_length=200, verbose_name="Název projektu")
    description = models.TextField(verbose_name="Popis projektu", blank=True)
    is_closed = models.BooleanField(default=False, verbose_name="Uzavřený projekt")

    def __str__(self):
        return self.name


class WorkRecord(models.Model):
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_records",
        verbose_name="Projekt",
    )
    # start_time = models.DateTimeField(default=timezone.now)
    # end_time = models.DateTimeField(null=True, blank=True)
    # note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.title or f"WorkRecord #{self.id}"


class PhotoDocumentation(models.Model):
    work_record = models.ForeignKey(
        "WorkRecord", related_name="photos", on_delete=models.CASCADE
    )
    photo = models.ImageField(
        upload_to="photos/", null=True, blank=True, default="photos/default.jpg"
    )
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.description or f"Photo #{self.id}"


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        FOREMAN = "FOREMAN", "Stavbyvedoucí"
        WORKER = "WORKER", "Dělník"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)

    class Meta:
        unique_together = ("user", "project")

    def __str__(self):
        return f"{self.user} · {self.project} · {self.role}"
