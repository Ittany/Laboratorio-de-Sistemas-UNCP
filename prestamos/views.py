from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import DevolucionForm, PrestamoForm, RegistroPrestamoForm
from .models import Auditoria, Equipo, Laboratorio, Prestamo
from .security import audit, is_admin, is_asistente, is_docente, roles_required


def inicio(request):
    equipos = Equipo.objects.select_related('categoria', 'laboratorio')
    laboratorio = request.GET.get('laboratorio', '')
    estado = request.GET.get('estado', '')
    q = request.GET.get('q', '').strip()
    if q:
        equipos = equipos.filter(Q(codigo_patrimonial__icontains=q) | Q(nombre__icontains=q) | Q(categoria__nombre__icontains=q))
    if laboratorio.isdigit():
        equipos = equipos.filter(laboratorio_id=int(laboratorio))
    if estado in dict(Equipo.ESTADOS):
        equipos = equipos.filter(estado=estado)
    return render(request, 'prestamos/inicio.html', {
        'equipos': equipos, 'laboratorios': Laboratorio.objects.all(),
        'estados': Equipo.ESTADOS, 'filtro_lab': laboratorio,
        'filtro_estado': estado, 'q': q,
    })


@login_required
def panel(request):
    if not (is_admin(request.user) or is_asistente(request.user) or is_docente(request.user)):
        raise PermissionDenied('No tiene un rol asignado.')
    query = Prestamo.objects.select_related('docente', 'equipo', 'equipo__laboratorio')
    if is_docente(request.user) and not (is_admin(request.user) or is_asistente(request.user)):
        query = query.filter(docente=request.user)
    contexto = {
        'total_equipos': Equipo.objects.count(),
        'activos': query.filter(estado=Prestamo.ACTIVO).count(),
        'pendientes': query.filter(estado=Prestamo.PENDIENTE).count(),
        'vencidos': query.filter(estado=Prestamo.ACTIVO, fecha_devolucion_prevista__lt=timezone.localdate()).count(),
        'prestamos': query[:10],
    }
    return render(request, 'prestamos/panel.html', contexto)


@roles_required('docente', 'admin', 'asistente')
def listado_prestamos(request):
    prestamos = Prestamo.objects.select_related('docente', 'equipo', 'equipo__laboratorio')
    if is_docente(request.user) and not (is_admin(request.user) or is_asistente(request.user)):
        prestamos = prestamos.filter(docente=request.user)
    estado = request.GET.get('estado', '')
    if estado in dict(Prestamo.ESTADOS):
        prestamos = prestamos.filter(estado=estado)
    return render(request, 'prestamos/listado.html', {'prestamos': prestamos, 'estados': Prestamo.ESTADOS, 'filtro_estado': estado})


def _form_errors(form, error):
    if hasattr(error, 'message_dict'):
        for field, errors in error.message_dict.items():
            for msg in errors:
                if field in form.fields:
                    form.add_error(field, msg)
                else:
                    form.add_error(None, msg)
    else:
        form.add_error(None, str(error))


@roles_required('docente')
def solicitar(request):
    if request.method == 'POST':
        form = PrestamoForm(request.POST, docente=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Revalidar dentro de transacción para evitar aceptar stock desactualizado.
                    Equipo.objects.select_for_update().get(pk=form.cleaned_data['equipo'].pk)
                    prestamo = form.save(commit=False)
                    prestamo.docente = request.user
                    prestamo.estado = Prestamo.PENDIENTE
                    prestamo.registrado_por = request.user
                    prestamo.full_clean()
                    prestamo.save()
                    audit(request, 'SOLICITUD_PRESTAMO', f'Préstamo #{prestamo.pk}')
                messages.success(request, 'Solicitud registrada. Está pendiente de entrega por el asistente.')
                return redirect('prestamos')
            except ValidationError as error:
                _form_errors(form, error)
    else:
        form = PrestamoForm(docente=request.user, initial={'fecha_prestamo': timezone.localdate()})
    return render(request, 'prestamos/formulario.html', {'form': form, 'titulo': 'Solicitar préstamo', 'subtitulo': 'La solicitud quedará pendiente de entrega.'})


@roles_required('asistente')
def registrar(request):
    if request.method == 'POST':
        form = RegistroPrestamoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    Equipo.objects.select_for_update().get(pk=form.cleaned_data['equipo'].pk)
                    prestamo = form.save(commit=False)
                    prestamo.docente = form.cleaned_data['docente']
                    prestamo.estado = Prestamo.ACTIVO
                    prestamo.fecha_entrega = timezone.now()
                    prestamo.registrado_por = request.user
                    prestamo.full_clean()
                    prestamo.save()
                    audit(request, 'REGISTRO_PRESTAMO', f'Préstamo #{prestamo.pk}')
                messages.success(request, 'Préstamo registrado y equipo entregado.')
                return redirect('prestamos')
            except ValidationError as error:
                _form_errors(form, error)
    else:
        form = RegistroPrestamoForm(initial={'fecha_prestamo': timezone.localdate()})
    return render(request, 'prestamos/formulario.html', {'form': form, 'titulo': 'Registrar préstamo', 'subtitulo': 'Registre la entrega directa a un docente.'})


@roles_required('asistente')
@require_POST
def entregar(request, pk):
    with transaction.atomic():
        prestamo = get_object_or_404(Prestamo.objects.select_for_update(), pk=pk)
        if prestamo.estado != Prestamo.PENDIENTE:
            messages.error(request, 'Solo se pueden entregar solicitudes pendientes.')
        else:
            try:
                prestamo.estado = Prestamo.ACTIVO
                prestamo.fecha_entrega = timezone.now()
                prestamo.full_clean()
                prestamo.save(update_fields=['estado', 'fecha_entrega'])
                audit(request, 'ENTREGA_PRESTAMO', f'Préstamo #{pk}')
                messages.success(request, 'Equipo entregado correctamente.')
            except ValidationError as error:
                messages.error(request, f'No es posible entregar: {error}')
    return redirect('prestamos')


@roles_required('asistente')
def devolver(request, pk):
    prestamo = get_object_or_404(Prestamo.objects.select_related('docente', 'equipo'), pk=pk)
    if prestamo.estado != Prestamo.ACTIVO:
        messages.error(request, 'Solo se pueden devolver préstamos activos.')
        return redirect('prestamos')
    if request.method == 'POST':
        form = DevolucionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                bloqueado = Prestamo.objects.select_for_update().get(pk=pk)
                if bloqueado.estado != Prestamo.ACTIVO:
                    messages.error(request, 'Este préstamo ya fue procesado.')
                    return redirect('prestamos')
                bloqueado.estado = Prestamo.DEVUELTO
                bloqueado.fecha_devolucion_real = timezone.now()
                bloqueado.estado_retorno = form.cleaned_data['estado_retorno']
                bloqueado.observacion_retorno = form.cleaned_data['observacion_retorno']
                bloqueado.devuelto_por = request.user
                bloqueado.save(update_fields=['estado', 'fecha_devolucion_real', 'estado_retorno', 'observacion_retorno', 'devuelto_por'])
                if bloqueado.estado_retorno != Equipo.OPERATIVO:
                    Equipo.objects.filter(pk=bloqueado.equipo_id).update(estado=bloqueado.estado_retorno)
                audit(request, 'DEVOLUCION', f'Préstamo #{pk}; estado={bloqueado.estado_retorno}')
            messages.success(request, 'Devolución registrada correctamente.')
            return redirect('prestamos')
    else:
        form = DevolucionForm(initial={'estado_retorno': Equipo.OPERATIVO})
    return render(request, 'prestamos/devolucion.html', {'form': form, 'prestamo': prestamo})


@roles_required('docente', 'asistente', 'admin')
@require_POST
def cancelar(request, pk):
    with transaction.atomic():
        prestamo = get_object_or_404(Prestamo.objects.select_for_update(), pk=pk)
        autorizado = is_admin(request.user) or is_asistente(request.user) or (is_docente(request.user) and prestamo.docente_id == request.user.pk)
        if not autorizado:
            raise PermissionDenied('No puede cancelar solicitudes de otro docente.')
        if prestamo.estado != Prestamo.PENDIENTE:
            messages.error(request, 'Solo se pueden cancelar solicitudes pendientes.')
        else:
            prestamo.estado = Prestamo.CANCELADO
            prestamo.save(update_fields=['estado'])
            audit(request, 'CANCELACION', f'Préstamo #{pk}')
            messages.success(request, 'Solicitud cancelada.')
    return redirect('prestamos')


@roles_required('admin')
def reportes(request):
    por_laboratorio = Laboratorio.objects.annotate(total=Count('equipos__prestamos', distinct=True)).order_by('nombre')
    por_docente = (Prestamo.objects.values('docente__first_name', 'docente__last_name', 'docente__username')
                   .annotate(total=Count('id'), unidades=Sum('cantidad')).order_by('-total')[:30])
    return render(request, 'prestamos/reportes.html', {
        'por_laboratorio': por_laboratorio, 'por_docente': por_docente,
        'total': Prestamo.objects.count(), 'devoluciones': Prestamo.objects.filter(estado=Prestamo.DEVUELTO).count(),
    })


@roles_required('admin')
def auditoria(request):
    return render(request, 'prestamos/auditoria.html', {'eventos': Auditoria.objects.select_related('usuario')[:100]})
