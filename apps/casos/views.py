from django.conf import settings
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permisos import (
    EsAgente,
    LecturaCasos,
    LecturaPersonalEscrituraAdmin,
    debe_ocultar_datos_personales,
)

from . import exportes
from .filtros import CasoFilter, aplicar_filtros
from .models import (
    ESTADOS_NO_VIGENTES,
    Animal,
    Caso,
    Coincidencia,
    Denuncia,
    Documento,
    EnteDenuncia,
    Estado,
    EventoAuditoria,
    TipoEvento,
)
from .serializers import (
    AnimalSerializer,
    AuditoriaSerializer,
    CambioEstadoSerializer,
    CasoDetalleSerializer,
    CasoEscrituraSerializer,
    CasoListaSerializer,
    CoincidenciaDetalleSerializer,
    CoincidenciaSerializer,
    ConsolidarSerializer,
    DenunciaSerializer,
    DescartarSerializer,
    DesestimarSerializer,
    DocumentoSerializer,
    EnteDenunciaSerializer,
    SeguimientoSerializer,
    TipoEventoSerializer,
    ValidarDocumentoSerializer,
)
from .servicios import casos as servicio_casos
from .servicios import consolidacion
from .servicios.auditoria import registrar
from .servicios.excepciones import PosibleDuplicado


def verificar_edicion(usuario, caso):
    """Pendiente con el cliente: ¿un agente puede modificar un caso creado por otro organismo?
    Se controla con SIRAM_EDICION_ENTRE_ORGANISMOS (por defecto sí, como pide la narrativa de seguimiento)."""
    if getattr(settings, 'SIRAM_EDICION_ENTRE_ORGANISMOS', True):
        return
    if caso.organismo_id != usuario.organismo_id:
        raise PermissionDenied('Este caso fue registrado por otro organismo y no podés modificarlo.')


class CasoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Bandeja, ficha, alta y modificación de casos."""

    permission_classes = [LecturaCasos]
    lookup_field = 'numero'
    lookup_value_regex = r'C-\d{4}-\d{4,}'
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = CasoFilter
    ordering_fields = ['numero', 'fecha_hecho', 'creado_en', 'actualizado_en', 'estado']
    ordering = ['-anio', '-secuencia']  # por número de caso, del más reciente al más antiguo

    def get_queryset(self):
        base = Caso.objects.select_related('victima', 'organismo', 'tipo_evento', 'unificado_en', 'registrado_por')
        if self.action == 'list':
            return base.prefetch_related('animales')
        return base.prefetch_related(
            'animales', 'denuncias__ente', 'denuncias__realizada_por', 'documentos__cargado_por',
            'seguimientos__usuario',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return CasoListaSerializer
        if self.action in ('create', 'partial_update'):
            return CasoEscrituraSerializer
        return CasoDetalleSerializer

    def _detalle(self, pk, codigo=status.HTTP_200_OK):
        caso = self.get_queryset().get(pk=pk)  # recarga limpia: sin cachés de antes del cambio
        return Response(CasoDetalleSerializer(caso, context=self.get_serializer_context()).data, status=codigo)

    # --- Alta y modificación ---
    def create(self, request, *args, **kwargs):
        serializador = CasoEscrituraSerializer(data=request.data, context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        datos = dict(serializador.validated_data)
        confirmar = datos.pop('confirmar_duplicado', False)
        try:
            caso = servicio_casos.crear_caso(request.user, datos, confirmar_duplicado=confirmar)
        except PosibleDuplicado as exc:
            contexto = self.get_serializer_context()
            return Response(
                {
                    'codigo': 'posible_duplicado',
                    'detalle': 'Hay casos muy parecidos. Revisalos y, si corresponde, repetí el alta con confirmarDuplicado: true.',
                    'candidatos': [
                        {
                            'caso': CasoListaSerializer(h.otro, context=contexto).data,
                            'tipo': h.tipo,
                            'fuerza': h.fuerza,
                            'puntaje': h.puntaje,
                            'senales': h.senales,
                        }
                        for h in exc.hallazgos
                    ],
                },
                status=status.HTTP_409_CONFLICT,
            )
        return self._detalle(caso.pk, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        caso = self.get_object()
        verificar_edicion(request.user, caso)
        serializador = CasoEscrituraSerializer(
            caso, data=request.data, partial=True, context=self.get_serializer_context()
        )
        serializador.is_valid(raise_exception=True)
        datos = dict(serializador.validated_data)
        datos.pop('confirmar_duplicado', None)
        servicio_casos.actualizar_caso(request.user, caso, datos)
        return self._detalle(caso.pk)

    # --- Contadores del menú y de los chips ---
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=['get'], pagination_class=None)
    def contadores(self, request):
        """Mismos criterios que las listas de trabajo: incompletos, duplicados y relacionados cuentan solo vigentes.
        Acepta los filtros de la bandeja (p. ej. `q`, `organismo`, `desde`) para que los chips respeten la búsqueda."""
        base = aplicar_filtros(request, Caso.objects.all())
        vigentes = base.vigentes()
        return Response(
            {
                'incompleto': vigentes.filter(incompleto=True).count(),
                'duplicado': vigentes.filter(marca_duplicado=True).count(),
                'relacionado': vigentes.filter(marca_relacionado=True).count(),
                'en_seguimiento': base.filter(estado=Estado.EN_SEGUIMIENTO).count(),
                'todos': base.count(),
            }
        )

    # --- Estado ---
    @extend_schema(request=CambioEstadoSerializer, responses=CasoDetalleSerializer)
    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, numero=None):
        caso = self.get_object()
        verificar_edicion(request.user, caso)
        serializador = CambioEstadoSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        d = serializador.validated_data
        servicio_casos.cambiar_estado(request.user, caso, d['estado'], d['motivo_espera'], d['motivo'])
        return self._detalle(caso.pk)

    @extend_schema(request=DesestimarSerializer, responses=CasoDetalleSerializer)
    @action(detail=True, methods=['post'])
    def desestimar(self, request, numero=None):
        """Única forma de «dar de baja» un caso: no se borra nada. El motivo es obligatorio."""
        caso = self.get_object()
        verificar_edicion(request.user, caso)
        serializador = DesestimarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        servicio_casos.cambiar_estado(request.user, caso, Estado.DESESTIMADO, motivo=serializador.validated_data['motivo'])
        return self._detalle(caso.pk)

    # --- Auditoría (R.29) ---
    @extend_schema(responses=AuditoriaSerializer(many=True))
    @action(detail=True, methods=['get'], permission_classes=[EsAgente], pagination_class=None)
    def auditoria(self, request, numero=None):
        caso = self.get_object()
        eventos = caso.auditoria.select_related('usuario')
        return Response(AuditoriaSerializer(eventos, many=True).data)

    # --- Animales, denuncias, documentos, seguimientos ---
    @extend_schema(request=AnimalSerializer, responses=AnimalSerializer(many=True))
    @action(detail=True, methods=['get', 'post'], pagination_class=None)
    def animales(self, request, numero=None):
        caso = self.get_object()
        if request.method == 'POST':
            verificar_edicion(request.user, caso)
            serializador = AnimalSerializer(data=request.data, context=self.get_serializer_context())
            serializador.is_valid(raise_exception=True)
            animal = servicio_casos.agregar_animal(request.user, caso, dict(serializador.validated_data))
            return Response(
                AnimalSerializer(animal, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED
            )
        return Response(AnimalSerializer(caso.animales.all(), many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=DenunciaSerializer, responses=DenunciaSerializer(many=True))
    @action(detail=True, methods=['get', 'post'], pagination_class=None)
    def denuncias(self, request, numero=None):
        caso = self.get_object()
        if request.method == 'POST':
            verificar_edicion(request.user, caso)
            serializador = DenunciaSerializer(data=request.data, context=self.get_serializer_context())
            serializador.is_valid(raise_exception=True)
            denuncia = servicio_casos.agregar_denuncia(request.user, caso, dict(serializador.validated_data))
            return Response(
                DenunciaSerializer(denuncia, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED
            )
        return Response(DenunciaSerializer(caso.denuncias.all(), many=True, context=self.get_serializer_context()).data)

    @extend_schema(request={'multipart/form-data': DocumentoSerializer}, responses=DocumentoSerializer(many=True))
    @action(
        detail=True, methods=['get', 'post'], parser_classes=[MultiPartParser, FormParser],
        permission_classes=[EsAgente], pagination_class=None,
    )
    def documentos(self, request, numero=None):
        caso = self.get_object()
        if request.method == 'POST':
            verificar_edicion(request.user, caso)
            serializador = DocumentoSerializer(data=request.data, context=self.get_serializer_context())
            serializador.is_valid(raise_exception=True)
            d = serializador.validated_data
            documento = servicio_casos.agregar_documento(request.user, caso, d['tipo'], d['archivo'])
            return Response(
                DocumentoSerializer(documento, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED
            )
        return Response(DocumentoSerializer(caso.documentos.all(), many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=SeguimientoSerializer, responses=SeguimientoSerializer(many=True))
    @action(detail=True, methods=['get', 'post'], permission_classes=[EsAgente], pagination_class=None)
    def seguimientos(self, request, numero=None):
        caso = self.get_object()
        if request.method == 'POST':
            verificar_edicion(request.user, caso)
            serializador = SeguimientoSerializer(data=request.data)
            serializador.is_valid(raise_exception=True)
            seguimiento = servicio_casos.agregar_seguimiento(request.user, caso, serializador.validated_data['descripcion'])
            return Response(SeguimientoSerializer(seguimiento).data, status=status.HTTP_201_CREATED)
        return Response(SeguimientoSerializer(caso.seguimientos.select_related('usuario'), many=True).data)

    # --- R.28: documento PDF del caso ---
    @extend_schema(responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=True, methods=['get'], url_path='ficha-pdf', permission_classes=[EsAgente])
    def ficha_pdf(self, request, numero=None):
        caso = self.get_object()
        registrar(caso, request.user, EventoAuditoria.Accion.DOCUMENTO_DESCARGADO, {'documento': 'ficha_pdf'})
        respuesta = HttpResponse(exportes.ficha_pdf(caso), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{caso.numero}.pdf"'
        return respuesta


class AnimalViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Animal.objects.select_related('caso')
    serializer_class = AnimalSerializer
    permission_classes = [LecturaCasos]
    http_method_names = ['get', 'patch', 'head', 'options']

    def partial_update(self, request, pk=None):
        animal = self.get_object()
        verificar_edicion(request.user, animal.caso)
        serializador = AnimalSerializer(animal, data=request.data, partial=True, context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        animal = servicio_casos.actualizar_animal(request.user, animal, dict(serializador.validated_data))
        return Response(AnimalSerializer(animal, context=self.get_serializer_context()).data)


class DenunciaViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Denuncia.objects.select_related('caso', 'ente', 'realizada_por')
    serializer_class = DenunciaSerializer
    permission_classes = [LecturaCasos]
    http_method_names = ['get', 'patch', 'head', 'options']

    def partial_update(self, request, pk=None):
        denuncia = self.get_object()
        verificar_edicion(request.user, denuncia.caso)
        serializador = DenunciaSerializer(denuncia, data=request.data, partial=True, context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        denuncia = servicio_casos.actualizar_denuncia(request.user, denuncia, dict(serializador.validated_data))
        return Response(DenunciaSerializer(denuncia, context=self.get_serializer_context()).data)


class DocumentoViewSet(viewsets.GenericViewSet):
    """Los certificados médicos NO se sirven por URL pública: se descargan acá, con permisos y auditoría."""

    queryset = Documento.objects.select_related('caso', 'cargado_por')
    serializer_class = DocumentoSerializer
    permission_classes = [EsAgente]
    http_method_names = ['get', 'patch', 'head', 'options']

    def retrieve(self, request, pk=None):
        return Response(DocumentoSerializer(self.get_object(), context=self.get_serializer_context()).data)

    @extend_schema(request=ValidarDocumentoSerializer, responses=DocumentoSerializer)
    def partial_update(self, request, pk=None):
        documento = self.get_object()
        verificar_edicion(request.user, documento.caso)
        serializador = ValidarDocumentoSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        servicio_casos.validar_documento(request.user, documento, serializador.validated_data['estado_validacion'])
        return Response(DocumentoSerializer(documento, context=self.get_serializer_context()).data)

    @extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY})
    @action(detail=True, methods=['get'])
    def descargar(self, request, pk=None):
        documento = self.get_object()
        registrar(
            documento.caso, request.user, EventoAuditoria.Accion.DOCUMENTO_DESCARGADO, {'documento': documento.pk}
        )
        nombre = documento.nombre_original or f'documento-{documento.pk}'
        return FileResponse(documento.archivo.open('rb'), as_attachment=True, filename=nombre)


class CoincidenciaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Posibles duplicados y eventos relacionados. Parámetros de la lista:
    `tipo` (duplicado|relacionado), `estado` (pendiente por defecto, o `todos`), `caso` (número de caso)."""

    permission_classes = [LecturaCasos]
    filter_backends = []

    def get_queryset(self):
        qs = Coincidencia.objects.select_related(
            'caso_a__victima', 'caso_a__organismo', 'caso_a__unificado_en',
            'caso_b__victima', 'caso_b__organismo', 'caso_b__unificado_en',
        ).prefetch_related('caso_a__animales', 'caso_b__animales')
        if self.action == 'list':
            params = self.request.query_params
            estado = params.get('estado', Coincidencia.Estado.PENDIENTE)
            if estado != 'todos':
                qs = qs.filter(estado=estado)
            if estado == Coincidencia.Estado.PENDIENTE:
                qs = qs.exclude(caso_a__estado__in=ESTADOS_NO_VIGENTES).exclude(caso_b__estado__in=ESTADOS_NO_VIGENTES)
            if params.get('tipo') in Coincidencia.Tipo.values:
                qs = qs.filter(tipo=params['tipo'])
            if params.get('caso'):
                qs = qs.filter(Q(caso_a__numero=params['caso']) | Q(caso_b__numero=params['caso']))
        else:
            qs = qs.prefetch_related(
                'caso_a__denuncias__ente', 'caso_a__denuncias__realizada_por', 'caso_a__documentos__cargado_por',
                'caso_a__seguimientos__usuario', 'caso_b__denuncias__ente', 'caso_b__denuncias__realizada_por',
                'caso_b__documentos__cargado_por', 'caso_b__seguimientos__usuario',
            ).select_related('caso_a__tipo_evento', 'caso_a__registrado_por', 'caso_b__tipo_evento', 'caso_b__registrado_por')
        return qs

    def get_serializer_class(self):
        return CoincidenciaSerializer if self.action == 'list' else CoincidenciaDetalleSerializer

    def _respuesta(self, pk):
        coincidencia = self.get_queryset().get(pk=pk)
        return Response(CoincidenciaDetalleSerializer(coincidencia, context=self.get_serializer_context()).data)

    @extend_schema(request=ConsolidarSerializer, responses=CoincidenciaDetalleSerializer)
    @action(detail=True, methods=['post'])
    def consolidar(self, request, pk=None):
        """Funde dos casos que son el mismo incidente. IRREVERSIBLE. Solo para posibles duplicados."""
        coincidencia = self.get_object()
        serializador = ConsolidarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        d = serializador.validated_data
        consolidacion.consolidar(
            coincidencia, request.user, superviviente=d['superviviente'], campos=d['campos'], confirmacion=d['confirmacion']
        )
        return self._respuesta(coincidencia.pk)

    @extend_schema(request=None, responses=CoincidenciaDetalleSerializer)
    @action(detail=True, methods=['post'])
    def vincular(self, request, pk=None):
        """Enlaza dos eventos relacionados sin fundirlos. Reversible."""
        consolidacion.vincular(self.get_object(), request.user)
        return self._respuesta(pk)

    @extend_schema(request=None, responses=CoincidenciaDetalleSerializer)
    @action(detail=True, methods=['post'])
    def desvincular(self, request, pk=None):
        consolidacion.desvincular(self.get_object(), request.user)
        return self._respuesta(pk)

    @extend_schema(request=DescartarSerializer, responses=CoincidenciaDetalleSerializer)
    @action(detail=True, methods=['post'])
    def descartar(self, request, pk=None):
        """«No están relacionados»: quita la marca."""
        serializador = DescartarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        consolidacion.descartar(self.get_object(), request.user, serializador.validated_data['nota'])
        return self._respuesta(pk)


# --- Catálogos (Administración › Tipos de evento) -----------------------------------------------------------------
class TipoEventoViewSet(viewsets.ModelViewSet):
    queryset = TipoEvento.objects.all()
    serializer_class = TipoEventoSerializer
    permission_classes = [LecturaPersonalEscrituraAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    pagination_class = None
    filterset_fields = ['activo']


class EnteDenunciaViewSet(viewsets.ModelViewSet):
    queryset = EnteDenuncia.objects.all()
    serializer_class = EnteDenunciaSerializer
    permission_classes = [LecturaPersonalEscrituraAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    pagination_class = None
    filterset_fields = ['activo']
