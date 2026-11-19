from datetime import date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Laboratorio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    ubicacion = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Laboratorio'
        verbose_name_plural = 'Laboratorios'

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=90, unique=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Equipo(models.Model):
    OPERATIVO = 'operativo'
    MANTENIMIENTO = 'mantenimiento'
    BAJA = 'baja'
    ESTADOS = [(OPERATIVO, 'Operativo'), (MANTENIMIENTO, 'En mantenimiento'), (BAJA, 'Dado de baja')]
    codigo_patrimonial = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    marca = models.CharField(max_length=90)
    modelo = models.CharField(max_length=90)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='equipos')
    estado = models.CharField(max_length=20, choices=ESTADOS, default=OPERATIVO)
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name='equipos')
    stock_total = models.PositiveIntegerField(default=1)
    ultimo_mantenimiento = models.DateField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['codigo_patrimonial']
        verbose_name = 'Equipo'
        constraints = [models.CheckConstraint(condition=models.Q(stock_total__gte=1), name='equipo_stock_positivo')]

    def __str__(self):
        return f'{self.codigo_patrimonial} · {self.nombre}'

    @property
    def dias_desde_mantenimiento(self):
        if not self.ultimo_mantenimiento:
            return None
        return max(0, (timezone.localdate() - self.ultimo_mantenimiento).days)

    @property
    def unidades_comprometidas(self):
        return self.prestamos.filter(estado__in=[Prestamo.PENDIENTE, Prestamo.ACTIVO]).aggregate(total=Sum('cantidad'))['total'] or 0

    @property
    def disponibles(self):
        if self.estado != self.OPERATIVO:
            return 0
        return max(0, self.stock_total - self.unidades_comprometidas)

    def clean(self):
        if self.stock_total is not None and self.stock_total < 1:
            raise ValidationError({'stock_total': 'El stock debe ser mayor a cero.'})
        if self.pk and self.stock_total is not None:
            comprometido = self.unidades_comprometidas
            if self.stock_total < comprometido:
                raise ValidationError({'stock_total': f'Existen {comprometido} unidades reservadas o prestadas.'})


class Prestamo(models.Model):
    PENDIENTE = 'pendiente'
    ACTIVO = 'activo'
    DEVUELTO = 'devuelto'
    CANCELADO = 'cancelado'
    ESTADOS = [
        (PENDIENTE, 'Pendiente'), (ACTIVO, 'En préstamo'),
        (DEVUELTO, 'Devuelto'), (CANCELADO, 'Cancelado'),
    ]
    docente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prestamos_solicitados')
    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, related_name='prestamos')
    cantidad = models.PositiveIntegerField(default=1)
    fecha_prestamo = models.DateField()
    fecha_devolucion_prevista = models.DateField()
    estado = models.CharField(max_length=15, choices=ESTADOS, default=PENDIENTE)
    observaciones = models.TextField(blank=True, max_length=1200)
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    fecha_devolucion_real = models.DateTimeField(null=True, blank=True)
    estado_retorno = models.CharField(max_length=20, choices=Equipo.ESTADOS, blank=True)
    observacion_retorno = models.TextField(blank=True, max_length=1200)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='prestamos_registrados')
    devuelto_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='devoluciones_registradas')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado', '-pk']
        verbose_name = 'Préstamo'
        verbose_name_plural = 'Préstamos'
        constraints = [models.CheckConstraint(condition=models.Q(cantidad__gte=1), name='prestamo_cantidad_positiva')]

    def __str__(self):
        return f'Préstamo #{self.pk} · {self.docente.username} · {self.equipo.codigo_patrimonial}'

    @property
    def dias_retraso(self):
        if self.estado not in (self.PENDIENTE, self.ACTIVO):
            return 0
        return max(0, (timezone.localdate() - self.fecha_devolucion_prevista).days)

    @property
    def vencido(self):
        return self.estado == self.ACTIVO and self.dias_retraso > 0

    def clean(self):
        errors = {}
        if self.fecha_prestamo and self.fecha_devolucion_prevista and self.fecha_devolucion_prevista <= self.fecha_prestamo:
            errors['fecha_devolucion_prevista'] = 'La devolución prevista debe ser posterior al préstamo.'
        if self.cantidad is not None and self.cantidad < 1:
            errors['cantidad'] = 'Ingrese una cantidad mayor que cero.'
        if self.equipo_id and self.estado in (self.PENDIENTE, self.ACTIVO):
            if self.equipo.estado != Equipo.OPERATIVO:
                errors['equipo'] = 'El equipo debe encontrarse operativo.'
            reservado = self.equipo.prestamos.filter(estado__in=[self.PENDIENTE, self.ACTIVO]).exclude(pk=self.pk).aggregate(n=Sum('cantidad'))['n'] or 0
            if self.cantidad and self.cantidad > self.equipo.stock_total - reservado:
                errors['cantidad'] = f'Stock disponible insuficiente: {max(0, self.equipo.stock_total - reservado)}.'
        if self.docente_id and self.estado in (self.PENDIENTE, self.ACTIVO):
            existentes = Prestamo.objects.filter(docente_id=self.docente_id, estado__in=[self.PENDIENTE, self.ACTIVO]).exclude(pk=self.pk).count()
            if existentes >= 3:
                errors['docente'] = 'El docente ya tiene 3 solicitudes o préstamos vigentes.'
        if errors:
            raise ValidationError(errors)


class Auditoria(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    accion = models.CharField(max_length=80)
    detalle = models.CharField(max_length=250, blank=True)
    ruta = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'

    def __str__(self):
        return f'{self.fecha_hora:%Y-%m-%d %H:%M} {self.accion}'
