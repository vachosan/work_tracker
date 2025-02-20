from django.db import models
from django.utils import timezone

class Project(models.Model):
    name = models.CharField(max_length=200, verbose_name="Název projektu")
    description = models.TextField(verbose_name="Popis projektu", blank=True)

    def __str__(self):
        return self.name
    
class WorkRecord(models.Model):
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_records', verbose_name="Projekt")
    #start_time = models.DateTimeField(default=timezone.now)
    #end_time = models.DateTimeField(null=True, blank=True)
    #note = models.TextField(blank=True)

    def __str__(self):
        return self.title

class PhotoDocumentation(models.Model):
    work_record = models.ForeignKey(WorkRecord, related_name='photos', on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='photos/', null=True, blank=True)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.description
    
