"""Inicio, estadísticas, exportación y opciones de formularios (R.20, R.23, R.27, R.30)."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Organismo
from apps.accounts.permisos import EsAgenteOAnalista, EsPersonalSiram

from . import exportes
from .filtros import aplicar_filtros
from .models import Animal, Caso, Documento, EnteDenuncia, Estado, MotivoEspera, Persona, TipoEvento, TriEstado

FRANJAS = [(0, 4, '0 a 4'), (5, 14, '5 a 14'), (15, 24, '15 a 24'), (25, 44, '25 a 44'), (45, 64, '45 a 64'), (65, 200, '65 o más')]


def _opciones(choices):
    return [{'valor': valor, 'etiqueta': etiqueta} for valor, etiqueta in choices.choices]


def _contar(queryset, campo, choices=None, distinto='pk'):
    """[{clave, etiqueta, cantidad}] ordenado de mayor a menor."""
    etiquetas = dict(choices.choices) if choices else {}
    filas = queryset.values(campo).annotate(n=Count(distinto, distinct=True)).order_by('-n')
    return [
        {'clave': f[campo], 'etiqueta': etiquetas.get(f[campo], f[campo] or 'Sin dato'), 'cantidad': f['n']}
        for f in filas
    ]


class InicioView(APIView):
    """Panel de inicio: arriba lo que bloquea, abajo indicadores. Solo cifras agregadas (sin datos personales)."""

    permission_classes = [EsPersonalSiram]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        vigentes = Caso.objects.vigentes()
        hace_30 = timezone.now() - timedelta(days=30)
        return Response(
            {
                'bloqueantes': {
                    'incompletos': vigentes.filter(incompleto=True).count(),
                    'pendientes_contacto': vigentes.filter(
                        estado=Estado.EN_SEGUIMIENTO, motivo_espera=MotivoEspera.CONTACTO
                    ).count(),
                    'posibles_duplicados': vigentes.filter(marca_duplicado=True).count(),
                    'eventos_relacionados': vigentes.filter(marca_relacionado=True).count(),
                },
                'indicadores': {
                    'casos_vigentes': vigentes.count(),
                    'ultimos_30_dias': vigentes.filter(fecha_hecho__gte=hace_30).count(),
                    'en_seguimiento': vigentes.filter(estado=Estado.EN_SEGUIMIENTO).count(),
                    'finalizados': vigentes.filter(estado=Estado.FINALIZADO).count(),
                },
                # Dato de cobertura (qué organismos cargan casos), no epidemiológico.
                'origen_registro': _contar(vigentes, 'organismo__nombre'),
            }
        )


class EstadisticasView(APIView):
    """Estadísticas sobre casos VIGENTES (los desestimados no cuentan; los unificados ya están en el caso que los absorbió).
    Acepta los mismos filtros que la bandeja: desde, hasta, ciudad, organismo, lesion, especie..."""

    permission_classes = [EsPersonalSiram]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        casos = aplicar_filtros(request, Caso.objects.vigentes())
        animales = Animal.objects.filter(caso__in=casos)

        por_mes = (
            casos.exclude(fecha_hecho=None).annotate(mes=TruncMonth('fecha_hecho')).values('mes')
            .annotate(n=Count('pk')).order_by('mes')
        )

        edades = [
            Persona(fecha_nacimiento=f['victima__fecha_nacimiento'], edad_declarada=f['victima__edad_declarada']).edad_al(f['fecha_hecho'])
            for f in casos.values('fecha_hecho', 'victima__fecha_nacimiento', 'victima__edad_declarada')
        ]
        franjas = [
            {'clave': etiqueta, 'etiqueta': etiqueta, 'cantidad': sum(1 for e in edades if e is not None and desde <= e <= hasta)}
            for desde, hasta, etiqueta in FRANJAS
        ]
        franjas.append({'clave': 'sin_dato', 'etiqueta': 'Sin dato', 'cantidad': sum(1 for e in edades if e is None)})

        return Response(
            {
                'total': casos.count(),
                'por_mes': [{'mes': f['mes'].strftime('%Y-%m'), 'cantidad': f['n']} for f in por_mes],
                'por_ciudad': _contar(casos, 'lugar_ciudad'),
                'por_lesion': _contar(casos, 'lesion', Caso.Lesion),
                'por_tipo_lugar': _contar(casos, 'tipo_lugar', Caso.TipoLugar),
                'por_situacion_persona': _contar(casos, 'situacion_persona', Caso.SituacionPersona),
                'por_sexo_victima': _contar(casos, 'victima__sexo', Persona.Sexo),
                'por_franja_etaria': franjas,
                'por_estado': _contar(casos, 'estado', Estado),
                'por_especie': _contar(animales, 'especie', Animal.Especie, distinto='caso'),
                'por_tenencia': _contar(animales, 'tenencia', Animal.Tenencia, distinto='caso'),
                # Variables de prevención y control (castración, chipeado, vacunación)
                'prevencion': {
                    'vacunacion': _contar(animales, 'vacunado', TriEstado, distinto='caso'),
                    'castracion': _contar(animales, 'castrado', TriEstado, distinto='caso'),
                    'con_identificacion': {
                        'si': animales.exclude(identificacion='').values('caso').distinct().count(),
                        'no': animales.filter(identificacion='').values('caso').distinct().count(),
                    },
                },
            }
        )


class ExportarView(APIView):
    """`?formato=csv|xlsx` más los filtros de la bandeja. Sin datos identificatorios (ver exportes.filas)."""

    permission_classes = [EsAgenteOAnalista]

    @extend_schema(
        parameters=[OpenApiParameter('formato', str, enum=['csv', 'xlsx'])],
        responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY},
    )
    def get(self, request):
        formato = request.query_params.get('formato', 'csv')
        if formato not in ('csv', 'xlsx'):
            raise ValidationError({'formato': 'Usá csv o xlsx.'})
        base = Caso.objects.all()
        if 'vigentes' not in request.query_params:
            base = base.vigentes()
        casos = aplicar_filtros(request, base).order_by('anio', 'secuencia')
        fecha = timezone.localdate().isoformat()
        if formato == 'xlsx':
            contenido = exportes.a_xlsx(casos)
            tipo = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            contenido = exportes.a_csv(casos)
            tipo = 'text/csv; charset=utf-8'
        respuesta = HttpResponse(contenido, content_type=tipo)
        respuesta['Content-Disposition'] = f'attachment; filename="siram-casos-{fecha}.{formato}"'
        return respuesta


class OpcionesView(APIView):
    """Valores para armar selects y chips del front (los definitivos viven acá, no en el front)."""

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                'estados': _opciones(Estado),
                'motivos_espera': _opciones(MotivoEspera),
                'marcas': [
                    {'valor': 'incompleto', 'etiqueta': 'Incompleto'},
                    {'valor': 'duplicado', 'etiqueta': 'Posible duplicado'},
                    {'valor': 'relacionado', 'etiqueta': 'Posible evento relacionado'},
                ],
                'tri_estado': _opciones(TriEstado),
                'sexos': _opciones(Persona.Sexo),
                'tipos_lugar': _opciones(Caso.TipoLugar),
                'situaciones_persona': _opciones(Caso.SituacionPersona),
                'lesiones': _opciones(Caso.Lesion),
                'gravedades': _opciones(Caso.Gravedad),
                'hizo_denuncia': _opciones(Caso.HizoDenuncia),
                'especies': _opciones(Animal.Especie),
                'tamanos': _opciones(Animal.Tamano),
                'tenencias': _opciones(Animal.Tenencia),
                'tipos_documento': _opciones(Documento.Tipo),
                'estados_validacion': _opciones(Documento.EstadoValidacion),
                'tipos_evento': list(TipoEvento.objects.filter(activo=True).values('id', 'nombre')),
                'entes': list(EnteDenuncia.objects.filter(activo=True).values('id', 'nombre')),
                'organismos': list(Organismo.objects.filter(activo=True).values('id', 'nombre')),
            }
        )
