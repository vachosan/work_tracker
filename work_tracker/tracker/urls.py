from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_work_record, name='create_work_record'),
    path('<int:pk>/', views.work_record_detail, name='work_record_detail'),
]
