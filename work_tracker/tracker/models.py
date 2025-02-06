from django.db import models
from django.utils import timezone

class WorkRecord(models.Model):
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.now)
    #start_time = models.DateTimeField(default=timezone.now)
    #end_time = models.DateTimeField(null=True, blank=True)
    #note = models.TextField(blank=True)

    def __str__(self):
        return self.title

class PhotoDocumentation(models.Model):
    work_record = models.ForeignKey(WorkRecord, related_name='photos', on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='work_photos/')
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.description