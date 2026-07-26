"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView

favicon_url = f"/{settings.STATIC_URL.strip('/')}/frontend/images/next-uniq-bd.png?v=2"

urlpatterns = [
    path(
        'favicon.ico',
        RedirectView.as_view(url=favicon_url, permanent=True),
        name='favicon',
    ),
    path('admin/', admin.site.urls),
    path('', include('blog.urls')),
    path('', include('category.urls')),
    path('', include('accounts.urls')),
    path('dashboard/accounts/', include(('finance.urls', 'finance'), namespace='finance')),
    path('', include('orders.urls')),
    path('', include('carousel.urls')),
    path('', include('company.urls')),
    path('', include('purchase.urls')),
    path('', include('sitepages.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
