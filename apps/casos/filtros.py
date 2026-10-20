import django_filters as df
from django.conf import settings
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.accounts.permisos import debe_ocultar_datos_personales

from .models import Animal, Caso, Estado, MotivoEspera
from .utiles import normalizar, solo_digitos

# En PostgreSQL la búsqueda ignora tildes (extensión `unaccent`, ver migración 0002); en SQLite (solo
# desarrollo) distingue «Nicolás» de «Nicolas».
CONTIENE = 'unaccent__icontains' if settings.USA_POSTGRES else 'icontains'

MARCAS = {'incompleto': 'incompleto', 'duplicado': 'marca_duplicado', 'relacionado': 'marca_relacionado'}


class CasoFilter(df.FilterSet):
    """Filtros de la bandeja y de las consultas (R.20). Todos opcionales y combinables.

    Los chips de la Bandeja equivalen a:
      Todos → (nada) · Incompletos → marca=incompleto · Posibles duplicados → marca=duplicado ·
      Eventos relacionados → marca=relacionado · En seguimiento → estado=en_seguimiento
    «marca» devuelve solo casos vigentes, igual que los contadores del menú.
    """

    q = df.CharFilter(method='buscar', label='Texto libre')
    estado = df.MultipleChoiceFilter(choices=Estado.choices)
    motivo_espera = df.ChoiceFilter(choices=MotivoEspera.choices)
    marca = df.ChoiceFilter(choices=[(k, k) for k in MARCAS], method='por_marca')
    vigentes = df.BooleanFilter(method='solo_vigentes')
    organismo = df.NumberFilter(field_name='organismo_id')
    tipo_evento = df.NumberFilter(field_name='tipo_evento_id')
    lesion = df.ChoiceFilter(choices=Caso.Lesion.choices)
    tipo_lugar = df.ChoiceFilter(choices=Caso.TipoLugar.choices)
    situacion_persona = df.ChoiceFilter(choices=Caso.SituacionPersona.choices)
    especie = df.ChoiceFilter(field_name='animales__especie', choices=Animal.Especie.choices, distinct=True)
    ciudad = df.CharFilter(field_name='lugar_ciudad', lookup_expr='icontains')
    desde = df.DateFilter(field_name='fecha_hecho', lookup_expr='date__gte')
    hasta = df.DateFilter(field_name='fecha_hecho', lookup_expr='date__lte')

    class Meta:
        model = Caso
        fields = []

    def buscar(self, queryset, nombre, valor):
        usuario = getattr(self.request, 'user', None)
        puede_buscar_dni = usuario is not None and usuario.is_authenticated and not debe_ocultar_datos_personales(usuario)
        for termino in normalizar(valor).split():
            condicion = (
                Q(numero__icontains=termino)
                | Q(**{f'victima__nombre__{CONTIENE}': termino})
                | Q(**{f'victima__apellido__{CONTIENE}': termino})
                | Q(**{f'lugar_direccion__{CONTIENE}': termino})
                | Q(**{f'lugar_ciudad__{CONTIENE}': termino})
                | Q(**{f'organismo__nombre__{CONTIENE}': termino})
            )
            if puede_buscar_dni and solo_digitos(termino) == termino:
                condicion |= Q(victima__dni__startswith=termino)
            queryset = queryset.filter(condicion)
        return queryset

    def por_marca(self, queryset, nombre, valor):
        return queryset.vigentes().filter(**{MARCAS[valor]: True})

    def solo_vigentes(self, queryset, nombre, valor):
        return queryset.vigentes() if valor else queryset


def aplicar_filtros(request, queryset):
    """Para vistas que no son un ViewSet (estadísticas, exportación)."""
    filtro = CasoFilter(request.query_params, queryset=queryset, request=request)
    if not filtro.is_valid():
        raise ValidationError(filtro.errors)
    return filtro.qs
