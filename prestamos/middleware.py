import logging
from django.contrib import messages
from django.utils import timezone
from .models import Prestamo
from .security import audit, is_docente, user_ip

logger = logging.getLogger('prestamos')

class AuditAndOverdueMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and is_docente(request.user):
            session_key = '_alerta_vencidos_usuario'
            if request.session.get(session_key) != request.user.pk:
                vencidos = Prestamo.objects.filter(
                    docente=request.user, estado=Prestamo.ACTIVO,
                    fecha_devolucion_prevista__lt=timezone.localdate(),
                ).count()
                if vencidos:
                    messages.warning(request, f'Tiene {vencidos} préstamo(s) vencido(s). Coordine la devolución con el laboratorio.')
                request.session[session_key] = request.user.pk
        response = self.get_response(request)
        if response.status_code in (401, 403) and request.user.is_authenticated:
            logger.warning('ACCESO DENEGADO usuario=%s ip=%s ruta=%s', request.user.username, user_ip(request), request.path)
            audit(request, 'ACCESO_DENEGADO', f'HTTP {response.status_code}')
        return response
