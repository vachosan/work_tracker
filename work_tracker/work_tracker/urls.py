"""
URL configuration for work_tracker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from tracker import views
from tracker import views_tiles

urlpatterns = [
    path('admin/', admin.site.urls),
    path('tiles-debug/whereis/<path:filename>', views_tiles.tiles_debug_whereis, name='tiles-debug-whereis'),
    path('tiles/<path:filename>', views_tiles.pmtiles_range_serve, name='pmtiles-range-serve'),
    path('tracker/', include('tracker.urls')),
    path('accounts/', include('allauth.urls')),  # Všechny cesty pro tracker
    path('', RedirectView.as_view(url='tracker/list/')),  # Přesměrování z kořenové adresy
    path('', views.home, name='home'),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # Přidání cesty pro soubory v MEDIA_ROOT

