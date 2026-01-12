from django.urls import path
from . import views
from . import views_tiles

urlpatterns = [
    # PMTiles (Range-enabled) and debug helpers must stay above other routes (avoid catch-alls)
    path("tiles/<path:path>", views_tiles.pmtiles_range_serve, name="pmtiles_range_serve"),
    path("tiles-debug/pmtiles", views_tiles.pmtiles_debug, name="pmtiles_debug"),
    path("tiles-debug/glyph", views_tiles.glyph_debug, name="glyph_debug"),
    path('create/', views.create_work_record, name='create_work_record'),
    path('create/<int:project_id>/', views.create_work_record, name='create_work_record_for_project'),
    path('trees/<int:tree_id>/interventions/new/', views.tree_intervention_create, name='tree_intervention_create'),
    path('api/trees/<int:tree_id>/interventions/', views.tree_intervention_api, name='tree_intervention_api'),
    path('interventions/<int:pk>/edit/', views.tree_intervention_update, name='tree_intervention_update'),
    path('<int:pk>/', views.work_record_detail, name='work_record_detail'),
    path('<int:pk>/edit/', views.edit_work_record, name='edit_work_record'),
    path('photo/<int:pk>/delete/', views.delete_photo, name='delete_photo'),
    path('list/', views.work_record_list, name='work_record_list'),
    path('projects/unassigned/', views.unassigned_work_records_list, name='unassigned_work_records_list'),
    path('project/create/', views.create_project, name='create_project'),
    path('project/<int:pk>/close/', views.close_project, name='close_project'),
    path('project/<int:pk>/activate/', views.activate_project, name='activate_project'),
    path('project/<int:pk>/delete/', views.delete_project, name='delete_project'),
    path('project/<int:pk>/purge/', views.purge_project, name='purge_project'),
    path('project/<int:pk>/edit/', views.edit_project, name='edit_project'),
    path('project/<int:pk>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    # duplicitn route odstranena
    path('projects/closed/', views.closed_projects_list, name='closed_projects_list'),
    path('project/<int:pk>/', views.project_detail, name='project_detail'),
    path('project/<int:pk>/export_zip/', views.export_selected_zip, name='export_selected_zip'),
    path('project/<int:pk>/export_csv/', views.export_selected_csv, name='export_selected_csv'),
    path('project/<int:pk>/export_xml/', views.export_selected_xml, name='export_selected_xml'),
    path('project/<int:pk>/export_xlsx/', views.export_selected_xlsx, name='export_selected_xlsx'),
    path('project/<int:pk>/items/', views.project_detail_items, name='project_detail_items'),
    path('project/<int:pk>/bulk-approve-interventions/', views.bulk_approve_interventions, name='bulk_approve_interventions'),
    path('project/<int:pk>/bulk-handover-interventions/', views.bulk_handover_interventions, name='bulk_handover_interventions'),
    path('project/<int:pk>/bulk-complete-interventions/', views.bulk_complete_interventions, name='bulk_complete_interventions'),
    path('projects/<int:project_pk>/trees/<int:workrecord_pk>/add/', views.project_tree_add, name='project_tree_add'),
    # testovac mapy endpoints odstranny
    path("map-leaflet/", views.map_leaflet_test, name="map_leaflet_test"),
    path("map-gl-pilot/", views.map_gl_pilot, name="map_gl_pilot"),
    path("map-project/<int:pk>/", views.map_project_redirect, name="map_project_redirect"),
    path("api/workrecords.geojson", views.workrecords_geojson, name="workrecords_geojson"),
    path("api/gbif-taxons/", views.gbif_taxon_suggest, name="gbif_taxon_suggest"),
    path("save-coordinates/", views.save_coordinates, name="save_coordinates"),
    path("map-upload-photo/", views.map_upload_photo, name="map_upload_photo"),
    path("map-create-work-record/", views.map_create_work_record, name="map_create_work_record"),
    path(
        "work-records/<int:pk>/assessment/",
        views.workrecord_assessment_api,
        name="workrecord_assessment_api",
    ),
    path(
        "api/work-records/<int:pk>/",
        views.workrecord_detail_api,
        name="workrecord_detail_api",
    ),
    path("workrecord/<int:pk>/delete/", views.delete_work_record, name="delete_work_record"),
    path("tiles/<path:path>", views_tiles.pmtiles_range_serve, name="pmtiles_range_serve"),


]
