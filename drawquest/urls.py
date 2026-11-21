from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "DrawQuest Admin"
admin.site.site_title = "DrawQuest"
admin.site.index_title = "Database admin"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# In development Django serves uploaded drawings. In production, serve MEDIA_ROOT
# from your web server (nginx, S3, etc.).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
