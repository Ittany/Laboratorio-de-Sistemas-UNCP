from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html
from .models import Auditoria, Categoria, Equipo, Laboratorio, Prestamo
from .security import audit


@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ubicacion')
    search_fields = ('nombre', 'ubicacion')


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ('nombre',)


@admin.action(description='Marcar equipos como en mantenimiento')
def poner_mantenimiento(modeladmin, request, queryset):
    disponibles = [equipo.pk for equipo in queryset if equipo.unidades_comprometidas == 0]
    actualizados = Equipo.objects.filter(pk__in=disponibles).update(estado=Equipo.MANTENIMIENTO)
    if actualizados:
        audit(request, 'MANTENIMIENTO_MASIVO', f'{actualizados} equipos')
    modeladmin.message_user(request, f'{actualizados} equipo(s) actualizados. Se omitieron equipos con reservas o préstamos.')


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ('codigo_patrimonial', 'nombre', 'categoria', 'laboratorio', 'estado_con_color', 'stock_total', 'stock_disponible', 'dias_mantenimiento')
    list_filter = ('laboratorio', 'estado', 'categoria')
    search_fields = ('codigo_patrimonial', 'nombre', 'categoria__nombre')
    list_select_related = ('categoria', 'laboratorio')
    actions = [poner_mantenimiento]

    @admin.display(description='Estado')
    def estado_con_color(self, obj):
        colors = {'operativo': '#176c4d', 'mantenimiento': '#a16400', 'baja': '#aa3343'}
        return format_html('<strong style="color:{}">{}</strong>', colors.get(obj.estado, '#444'), obj.get_estado_display())

    @admin.display(description='Disponible')
    def stock_disponible(self, obj):
        return obj.disponibles

    @admin.display(description='Días desde mantenimiento')
    def dias_mantenimiento(self, obj):
        return obj.dias_desde_mantenimiento if obj.dias_desde_mantenimiento is not None else 'Sin registro'

    def delete_model(self, request, obj):
        codigo = obj.codigo_patrimonial
        super().delete_model(request, obj)
        audit(request, 'ELIMINACION_EQUIPO', codigo)

    def delete_queryset(self, request, queryset):
        codigos = list(queryset.values_list('codigo_patrimonial', flat=True))
        super().delete_queryset(request, queryset)
        audit(request, 'ELIMINACION_MASIVA_EQUIPOS', ', '.join(codigos)[:250])


@admin.action(description='Enviar recordatorio de devolución (registro interno)')
def recordar_devolucion(modeladmin, request, queryset):
    seleccionados = queryset.filter(estado=Prestamo.ACTIVO)
    cantidad = seleccionados.count()
    # No se simula envío de correo: deja una constancia visible y auditable.
    for prestamo in seleccionados.select_related('docente', 'equipo'):
        audit(request, 'RECORDATORIO', f'Préstamo #{prestamo.pk} para {prestamo.docente.username}')
    modeladmin.message_user(request, f'{cantidad} recordatorio(s) registrados en auditoría. No se enviaron correos.', messages.INFO)


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ('id', 'docente', 'equipo', 'cantidad', 'fecha_prestamo', 'fecha_devolucion_prevista', 'estado', 'dias_retraso_admin')
    list_filter = ('fecha_prestamo', 'fecha_devolucion_prevista', 'estado', 'docente')
    search_fields = ('equipo__codigo_patrimonial', 'docente__username', 'docente__first_name', 'docente__last_name')
    list_select_related = ('docente', 'equipo')
    readonly_fields = ('docente', 'equipo', 'cantidad', 'fecha_prestamo', 'fecha_devolucion_prevista', 'estado', 'observaciones', 'fecha_entrega', 'fecha_devolucion_real', 'estado_retorno', 'observacion_retorno', 'registrado_por', 'devuelto_por', 'creado')
    actions = [recordar_devolucion]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Días de retraso')
    def dias_retraso_admin(self, obj):
        return obj.dias_retraso


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha_hora', 'usuario', 'ip', 'accion', 'detalle', 'ruta')
    list_filter = ('accion', 'fecha_hora')
    search_fields = ('usuario__username', 'accion', 'detalle')
    list_select_related = ('usuario',)
    readonly_fields = ('fecha_hora', 'usuario', 'ip', 'accion', 'detalle', 'ruta')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
