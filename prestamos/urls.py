from django.urls import path
from . import views
urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('panel/', views.panel, name='panel'),
    path('prestamos/', views.listado_prestamos, name='prestamos'),
    path('prestamos/solicitar/', views.solicitar, name='solicitar'),
    path('prestamos/registrar/', views.registrar, name='registrar'),
    path('prestamos/<int:pk>/entregar/', views.entregar, name='entregar'),
    path('prestamos/<int:pk>/devolver/', views.devolver, name='devolver'),
    path('prestamos/<int:pk>/cancelar/', views.cancelar, name='cancelar'),
    path('reportes/', views.reportes, name='reportes'),
    path('auditoria/', views.auditoria, name='auditoria'),
]
