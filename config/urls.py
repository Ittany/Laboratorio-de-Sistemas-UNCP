from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = 'FIS UNCP | Administración de laboratorios'
admin.site.site_title = 'Administración FIS UNCP'
admin.site.index_title = 'Gestión institucional'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/ingresar/', auth_views.LoginView.as_view(template_name='registration/login.html', redirect_authenticated_user=True), name='login'),
    path('cuentas/salir/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('prestamos.urls')),
]
