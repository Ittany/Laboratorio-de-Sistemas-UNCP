import logging
from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from .models import Auditoria

logger = logging.getLogger('prestamos')


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Administrador').exists())


def is_docente(user):
    return user.is_authenticated and user.groups.filter(name='Docente').exists()


def is_asistente(user):
    return user.is_authenticated and user.groups.filter(name='Asistente').exists()


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            allowed = ('admin' in roles and is_admin(request.user)) or ('docente' in roles and is_docente(request.user)) or ('asistente' in roles and is_asistente(request.user))
            if not allowed:
                raise PermissionDenied('No cuenta con permisos para realizar esta operación.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def user_ip(request):
    # REMOTE_ADDR no confía en encabezados X-Forwarded-For suministrados por terceros.
    return request.META.get('REMOTE_ADDR') or None


def audit(request, accion, detalle=''):
    Auditoria.objects.create(
        usuario=request.user if request.user.is_authenticated else None,
        ip=user_ip(request), accion=accion, detalle=str(detalle)[:250], ruta=request.path[:250],
    )
    logger.info('AUDITORÍA %s usuario=%s ip=%s detalle=%s', accion, request.user, user_ip(request), detalle)
