from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('create/', views.create_work_record, name='create_work_record'),
    path('create/<int:project_id>/', views.create_work_record, name='create_work_record_for_project'),
    path('<int:pk>/', views.work_record_detail, name='work_record_detail'),
    path('<int:pk>/edit/', views.edit_work_record, name='edit_work_record'),
    path('photo/<int:pk>/delete/', views.delete_photo, name='delete_photo'),
    path('list/', views.work_record_list, name='work_record_list'),
    path('project/create/', views.create_project, name='create_project'),
    path('project/<int:pk>/close/', views.close_project, name='close_project'),
    path('project/<int:pk>/activate/', views.activate_project, name='activate_project'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/signup/', views.signup, name='signup'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('project/<int:pk>/edit/', views.edit_project, name='edit_project'),
    path('project/<int:pk>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    path('project/<int:pk>/close/', views.close_project, name='close_project'),
    path('project/<int:pk>/activate/', views.activate_project, name='activate_project'),
    path('projects/closed/', views.closed_projects_list, name='closed_projects_list'),
    path('project/<int:pk>/', views.project_detail, name='project_detail'),


]

