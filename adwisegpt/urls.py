"""
URL configuration for adwisegpt project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static



# your_project/urls.py
from django.http import JsonResponse

def handler404(request, exception=None):
    return JsonResponse({
        "success": False,
        "message": "The endpoint you're looking for doesn't exist.",
        "errors": None,
        "data": None,
    }, status=404)

def handler500(request):
    return JsonResponse({
        "success": False,
        "message": "Internal server error. Please try again later.",
        "errors": None,
        "data": None,
    }, status=500)

def handler403(request, exception=None):
    return JsonResponse({
        "success": False,
        "message": "You do not have permission to access this resource.",
        "errors": None,
        "data": None,
    }, status=403)

def handler400(request, exception=None):
    return JsonResponse({
        "success": False,
        "message": "Bad request.",
        "errors": None,
        "data": None,
    }, status=400)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include("accounts.urls")),
    path('api/advertisers/', include('advertisers.urls')),
    path('api/user/', include('user.urls')), 
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



handler400 = handler400
handler403 = handler403
handler404 = handler404
handler500 = handler500