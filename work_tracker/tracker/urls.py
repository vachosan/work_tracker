from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_work_record, name='create_work_record'),
    path('<int:pk>/', views.work_record_detail, name='work_record_detail'),
    path('<int:pk>/edit/', views.edit_work_record, name='edit_work_record'),
    path('photo/<int:pk>/delete/', views.delete_photo, name='delete_photo'),
    path('list/', views.work_record_list, name='work_record_list'),
]