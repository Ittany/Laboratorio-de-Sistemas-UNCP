from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from prestamos.models import Categoria, Equipo, Laboratorio, Prestamo


class Command(BaseCommand):
    help = 'Carga 5 usuarios, 5 laboratorios, 10 equipos y 15 préstamos de demostración.'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='Cambiar2026!', help='Contraseña temporal para cuentas de demostración.')

    @transaction.atomic
    def handle(self, *args, **options):
        password = options['password']
        roles = {nombre: Group.objects.get_or_create(name=nombre)[0] for nombre in ['Administrador', 'Docente', 'Asistente']}
        User = get_user_model()
        datos = [
            ('adminfis', 'Administrador', 'Administración', 'FIS'),
            ('docente01', 'Docente', 'Ana', 'Quispe'),
            ('docente02', 'Docente', 'Luis', 'Rojas'),
            ('asistente01', 'Asistente', 'María', 'Huamán'),
            ('asistente02', 'Asistente', 'Carlos', 'Torres'),
        ]
        usuarios = {}
        for username, rol, nombre, apellido in datos:
            user, creado = User.objects.get_or_create(username=username, defaults={
                'first_name': nombre, 'last_name': apellido,
                'email': f'{username}@uncp.edu.pe',
                'is_staff': rol == 'Administrador', 'is_superuser': rol == 'Administrador',
            })
            if creado:
                user.set_password(password)
                user.save()
            user.groups.add(roles[rol])
            usuarios[username] = user
        labs = [Laboratorio.objects.get_or_create(nombre=f'Laboratorio de Cómputo {i}', defaults={'ubicacion': f'Pabellón FIS · Sala {i}'})[0] for i in range(1, 6)]
        categorias = {x: Categoria.objects.get_or_create(nombre=x)[0] for x in ['Laptop', 'Proyector', 'Cámara', 'Kit Arduino', 'Router', 'Switch']}
        inventario = [
            ('FIS-001', 'Laptop de docencia', 'Dell', 'Latitude 5420', 'Laptop', 0, 8),
            ('FIS-002', 'Proyector multimedia', 'Epson', 'PowerLite X49', 'Proyector', 0, 3),
            ('FIS-003', 'Kit de robótica Arduino', 'Arduino', 'Uno R3', 'Kit Arduino', 1, 12),
            ('FIS-004', 'Router empresarial', 'MikroTik', 'hEX S', 'Router', 1, 6),
            ('FIS-005', 'Cámara digital', 'Canon', 'EOS Rebel T7', 'Cámara', 2, 4),
            ('FIS-006', 'Switch administrable', 'Cisco', 'CBS250', 'Switch', 2, 5),
            ('FIS-007', 'Laptop de investigación', 'Lenovo', 'ThinkPad E14', 'Laptop', 3, 10),
            ('FIS-008', 'Proyector portátil', 'BenQ', 'MS550', 'Proyector', 3, 2),
            ('FIS-009', 'Kit sensores y Arduino', 'Arduino', 'Mega 2560', 'Kit Arduino', 4, 9),
            ('FIS-010', 'Switch de laboratorio', 'TP-Link', 'TL-SG108', 'Switch', 4, 8),
        ]
        equipos = []
        for codigo, nombre, marca, modelo, categoria, lab, stock in inventario:
            equipo, _ = Equipo.objects.get_or_create(codigo_patrimonial=codigo, defaults={
                'nombre': nombre, 'marca': marca, 'modelo': modelo,
                'categoria': categorias[categoria], 'laboratorio': labs[lab],
                'stock_total': stock, 'ultimo_mantenimiento': timezone.localdate() - timedelta(days=30+lab*11),
            })
            equipos.append(equipo)
        hoy = timezone.localdate()
        if not Prestamo.objects.exists():
            # 10 históricos devueltos y 5 vigentes, repartidos entre 2 docentes.
            for index in range(15):
                docente = usuarios['docente01'] if index % 2 == 0 else usuarios['docente02']
                equipo = equipos[index % len(equipos)]
                historico = index < 10
                inicio = hoy - timedelta(days=30 - index) if historico else hoy - timedelta(days=3)
                fin = inicio + timedelta(days=4) if historico else hoy + timedelta(days=3)
                prestamo = Prestamo.objects.create(
                    docente=docente, equipo=equipo, cantidad=1,
                    fecha_prestamo=inicio, fecha_devolucion_prevista=fin,
                    estado=Prestamo.DEVUELTO if historico else Prestamo.ACTIVO,
                    registrado_por=usuarios['asistente01'],
                    fecha_entrega=timezone.now() - timedelta(days=30-index),
                    observaciones='Registro de prueba para prácticas de laboratorio.',
                    fecha_devolucion_real=(timezone.now() - timedelta(days=25-index)) if historico else None,
                    estado_retorno=Equipo.OPERATIVO if historico else '',
                    devuelto_por=usuarios['asistente02'] if historico else None,
                )
        self.stdout.write(self.style.SUCCESS('Datos de demostración preparados: 5 usuarios, 5 laboratorios, 10 equipos y 15 préstamos.'))
        self.stdout.write('Cuentas: adminfis, docente01, docente02, asistente01 y asistente02')
        self.stdout.write('La contraseña se asigna solo a cuentas NUEVAS. Cámbiela después de iniciar sesión.')
