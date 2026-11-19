from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Categoria, Equipo, Laboratorio, Prestamo


class SistemaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.docente = User.objects.create_user('docente', password='Clave-Segura123')
        self.otro = User.objects.create_user('docente2', password='Clave-Segura123')
        self.asistente = User.objects.create_user('asistente', password='Clave-Segura123')
        self.administrador = User.objects.create_superuser('admin', 'admin@example.com', 'Clave-Segura123')
        for nombre, usuario in [('Docente', self.docente), ('Docente', self.otro), ('Asistente', self.asistente)]:
            grupo, _ = Group.objects.get_or_create(name=nombre)
            usuario.groups.add(grupo)
        self.equipo = Equipo.objects.create(
            codigo_patrimonial='TEST-001', nombre='Laptop', marca='Dell', modelo='5420',
            categoria=Categoria.objects.create(nombre='Laptop'),
            laboratorio=Laboratorio.objects.create(nombre='Laboratorio 1'), stock_total=3,
        )
        self.hoy = timezone.localdate()

    def crear(self, docente=None, estado=Prestamo.ACTIVO, cantidad=1, equipo=None):
        return Prestamo.objects.create(docente=docente or self.docente, equipo=equipo or self.equipo,
            cantidad=cantidad, fecha_prestamo=self.hoy, fecha_devolucion_prevista=self.hoy+timedelta(days=2), estado=estado)

    def test_catalogo_publico(self):
        self.assertEqual(self.client.get(reverse('inicio')).status_code, 200)

    def test_docente_solo_ve_sus_prestamos(self):
        ajeno = self.crear(docente=self.otro)
        self.client.force_login(self.docente)
        respuesta = self.client.get(reverse('prestamos'))
        self.assertNotContains(respuesta, f'#{ajeno.pk}')

    def test_asistente_puede_devolver_y_docente_no(self):
        p = self.crear()
        self.client.force_login(self.docente)
        self.assertEqual(self.client.post(reverse('devolver', args=[p.pk]), {'estado_retorno': 'operativo'}).status_code, 403)
        self.client.force_login(self.asistente)
        respuesta = self.client.post(reverse('devolver', args=[p.pk]), {'estado_retorno': 'operativo'})
        self.assertEqual(respuesta.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.estado, Prestamo.DEVUELTO)

    def test_maximo_tres_prestamos(self):
        # Reservas y préstamos son contabilizados para evitar sobrepasar el máximo al entregar.
        for _ in range(3):
            self.crear(estado=Prestamo.PENDIENTE)
        nuevo = Prestamo(docente=self.docente, equipo=self.equipo, cantidad=1,
            fecha_prestamo=self.hoy, fecha_devolucion_prevista=self.hoy+timedelta(days=2))
        with self.assertRaises(ValidationError):
            nuevo.full_clean()

    def test_stock_insuficiente(self):
        self.crear(cantidad=3)
        nuevo = Prestamo(docente=self.otro, equipo=self.equipo, cantidad=1,
            fecha_prestamo=self.hoy, fecha_devolucion_prevista=self.hoy+timedelta(days=2))
        with self.assertRaises(ValidationError):
            nuevo.full_clean()

    def test_fecha_invalida(self):
        nuevo = Prestamo(docente=self.docente, equipo=self.equipo, cantidad=1,
            fecha_prestamo=self.hoy, fecha_devolucion_prevista=self.hoy)
        with self.assertRaises(ValidationError):
            nuevo.full_clean()

    def test_reporte_solo_admin(self):
        self.client.force_login(self.docente)
        self.assertEqual(self.client.get(reverse('reportes')).status_code, 403)
        self.client.force_login(self.administrador)
        self.assertEqual(self.client.get(reverse('reportes')).status_code, 200)
