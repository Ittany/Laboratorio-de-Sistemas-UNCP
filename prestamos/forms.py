from django import forms
from django.contrib.auth import get_user_model
from django.utils.html import strip_tags
from .models import Equipo, Prestamo

class PrestamoForm(forms.ModelForm):
    class Meta:
        model = Prestamo
        fields = ['equipo', 'cantidad', 'fecha_prestamo', 'fecha_devolucion_prevista', 'observaciones']
        widgets = {
            'fecha_prestamo': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_devolucion_prevista': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Observaciones opcionales'}),
        }

    def __init__(self, *args, **kwargs):
        self.docente = kwargs.pop('docente')
        super().__init__(*args, **kwargs)
        self.fields['equipo'].queryset = Equipo.objects.filter(estado=Equipo.OPERATIVO).select_related('laboratorio', 'categoria')
        self.fields['equipo'].label = 'Equipo solicitado'
        self.fields['fecha_devolucion_prevista'].label = 'Fecha prevista de devolución'
        self.fields['fecha_prestamo'].label = 'Fecha de préstamo'
        self.fields['cantidad'].widget.attrs.update({'min': '1'})

    def clean_observaciones(self):
        return strip_tags(self.cleaned_data.get('observaciones', '')).strip()

    def clean(self):
        data = super().clean()
        if self.docente:
            instance = self.instance
            instance.docente = self.docente
            instance.equipo = data.get('equipo') if data.get('equipo') else instance.equipo
            instance.cantidad = data.get('cantidad') if data.get('cantidad') is not None else instance.cantidad
            instance.fecha_prestamo = data.get('fecha_prestamo')
            instance.fecha_devolucion_prevista = data.get('fecha_devolucion_prevista')
            instance.estado = Prestamo.PENDIENTE
            # ModelForm ejecutará full_clean() y mostrará errores asociados a los campos.
        return data

class RegistroPrestamoForm(PrestamoForm):
    docente = forms.ModelChoiceField(queryset=get_user_model().objects.none(), label='Docente')

    def __init__(self, *args, **kwargs):
        kwargs['docente'] = None
        super().__init__(*args, **kwargs)
        self.fields['docente'].queryset = get_user_model().objects.filter(groups__name='Docente', is_active=True).distinct().order_by('first_name', 'username')

    def clean(self):
        data = super().clean()
        if data.get('docente'):
            self.instance.docente = data['docente']
        return data

class DevolucionForm(forms.Form):
    estado_retorno = forms.ChoiceField(choices=Equipo.ESTADOS, label='Estado al devolver')
    observacion_retorno = forms.CharField(required=False, max_length=1200, label='Observación de devolución', widget=forms.Textarea(attrs={'rows': 3}))

    def clean_observacion_retorno(self):
        return strip_tags(self.cleaned_data.get('observacion_retorno', '')).strip()
