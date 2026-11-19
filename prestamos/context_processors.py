from .security import is_admin, is_asistente, is_docente

def roles(request):
    return {
        'es_admin': is_admin(request.user), 'es_asistente': is_asistente(request.user),
        'es_docente': is_docente(request.user),
    }
