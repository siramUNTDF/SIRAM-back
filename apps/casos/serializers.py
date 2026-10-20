from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.permisos import debe_ocultar_datos_personales

from .models import (
    Animal,
    Caso,
    Coincidencia,
    Denuncia,
    Documento,
    EnteDenuncia,
    Estado,
    EventoAuditoria,
    MotivoEspera,
    Persona,
    Seguimiento,
    TipoEvento,
)
from .servicios.completitud import completitud
from .utiles import iniciales, solo_digitos

TAMANO_MAXIMO_DOCUMENTO = 10 * 1024 * 1024  # 10 MB


def ocultar_datos(context):
    """R.16: el rol analista no ve datos identificatorios. Si no hay usuario en el contexto, se oculta."""
    if 'ocultar' in context:
        return context['ocultar']
    request = context.get('request')
    return True if request is None else debe_ocultar_datos_personales(request.user)


def _etiqueta(choices, valor):
    return dict(choices.choices).get(valor) if valor and valor != 'sin_dato' else None


# --- Bloques del caso ---------------------------------------------------------------------------------
class PersonaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Persona
        fields = [
            'id', 'nombre', 'apellido', 'dni', 'fecha_nacimiento', 'edad_declarada', 'sexo',
            'telefono', 'email', 'direccion', 'ciudad',
        ]
        read_only_fields = ['id']

    def validate_dni(self, valor):
        digitos = solo_digitos(valor)
        if valor and not 6 <= len(digitos) <= 9:
            raise serializers.ValidationError('El DNI debe tener entre 6 y 9 dígitos (sin puntos).')
        return digitos

    def validate_telefono(self, valor):
        if valor and len(solo_digitos(valor)) < 7:
            raise serializers.ValidationError('El teléfono debe tener al menos 7 dígitos.')
        return valor

    def validate_fecha_nacimiento(self, valor):
        if valor and valor > timezone.localdate():
            raise serializers.ValidationError('La fecha de nacimiento no puede ser futura.')
        return valor

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        if ocultar_datos(self.context):
            nombre_completo = instance.nombre_completo
            datos['nombre'] = iniciales(nombre_completo)
            datos['apellido'] = ''
            for campo in ('dni', 'fecha_nacimiento', 'telefono', 'email', 'direccion'):
                datos[campo] = None
        return datos


class AnimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Animal
        exclude = ['caso']
        read_only_fields = ['id']

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        if ocultar_datos(self.context):
            for campo in ('tenedor_nombre', 'tenedor_telefono', 'tenedor_direccion'):
                datos[campo] = None
        return datos


class DenunciaSerializer(serializers.ModelSerializer):
    ente_nombre = serializers.CharField(source='ente.nombre', read_only=True)
    realizada_por = PersonaSerializer(required=False, allow_null=True)

    class Meta:
        model = Denuncia
        fields = ['id', 'ente', 'ente_nombre', 'numero', 'fecha', 'realizada_por', 'vinculo', 'creado_en']
        read_only_fields = ['id', 'creado_en']

    def validate_ente(self, ente):
        if not ente.activo:
            raise serializers.ValidationError('Este ente ya no está disponible.')
        return ente


class DocumentoSerializer(serializers.ModelSerializer):
    archivo = serializers.FileField(write_only=True)
    cargado_por_nombre = serializers.CharField(source='cargado_por.nombre_completo', read_only=True)

    class Meta:
        model = Documento
        fields = [
            'id', 'tipo', 'archivo', 'nombre_original', 'cargado_por_nombre', 'cargado_en', 'estado_validacion',
        ]
        read_only_fields = ['id', 'nombre_original', 'cargado_en', 'estado_validacion']

    def validate_archivo(self, archivo):
        if archivo.size > TAMANO_MAXIMO_DOCUMENTO:
            raise serializers.ValidationError('El archivo supera los 10 MB.')
        cabecera = archivo.read(8)
        archivo.seek(0)
        firmas = (b'%PDF', b'\xff\xd8\xff', b'\x89PNG')
        if not cabecera.startswith(firmas):
            raise serializers.ValidationError('El contenido no corresponde a un PDF, JPG o PNG.')
        return archivo


class ValidarDocumentoSerializer(serializers.Serializer):
    estado_validacion = serializers.ChoiceField(choices=Documento.EstadoValidacion.choices)


class SeguimientoSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.nombre_completo', read_only=True)

    class Meta:
        model = Seguimiento
        fields = ['id', 'usuario_nombre', 'descripcion', 'creado_en']
        read_only_fields = ['id', 'creado_en']


class AuditoriaSerializer(serializers.ModelSerializer):
    usuario = serializers.SerializerMethodField()
    accion_etiqueta = serializers.CharField(source='get_accion_display', read_only=True)

    class Meta:
        model = EventoAuditoria
        fields = ['id', 'usuario', 'accion', 'accion_etiqueta', 'detalle', 'creado_en']

    def get_usuario(self, obj) -> str:
        return obj.usuario.nombre_completo if obj.usuario_id else 'Sistema'


# --- Caso: lista (bandeja) -------------------------------------------------------------------------------
class CasoListaSerializer(serializers.ModelSerializer):
    """Misma forma que los datos de ejemplo del front (src/mocks/casos.js): textos listos para mostrar."""

    id = serializers.CharField(source='numero', read_only=True)
    victima = serializers.SerializerMethodField()
    lugar = serializers.SerializerMethodField()
    animal = serializers.SerializerMethodField()
    lesion = serializers.SerializerMethodField()
    motivo_espera = serializers.SerializerMethodField()
    unificado_en = serializers.SerializerMethodField()
    origen = serializers.CharField(source='organismo.nombre', read_only=True)
    marcas = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Caso
        fields = [
            'id', 'fecha_hecho', 'victima', 'lugar', 'animal', 'lesion', 'estado', 'motivo_espera',
            'unificado_en', 'origen', 'marcas',
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_victima(self, obj):
        nombre = obj.victima.nombre_completo
        if ocultar_datos(self.context):
            nombre = iniciales(nombre)
        return {'nombre': nombre or None, 'edad': obj.victima.edad_al(obj.fecha_hecho)}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_lugar(self, obj):
        direccion = None if ocultar_datos(self.context) else (obj.lugar_direccion or None)
        return {'direccion': direccion, 'ciudad': obj.lugar_ciudad or None}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_animal(self, obj):
        animales = list(obj.animales.all())
        if not animales:
            return {'especie': None, 'tamano': None}
        primero = animales[0]
        return {
            'especie': primero.get_especie_display(),
            'tamano': _etiqueta(Animal.Tamano, primero.tamano),
        }

    def get_lesion(self, obj) -> str | None:
        return _etiqueta(Caso.Lesion, obj.lesion)

    def get_motivo_espera(self, obj) -> str | None:
        return obj.motivo_espera or None

    def get_unificado_en(self, obj) -> str | None:
        return obj.unificado_en.numero if obj.unificado_en_id else None


# --- Caso: ficha -----------------------------------------------------------------------------------------------
class CasoDetalleSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='numero', read_only=True)
    origen = serializers.CharField(source='organismo.nombre', read_only=True)
    registrado_por = serializers.SerializerMethodField()
    unificado_en = serializers.SerializerMethodField()
    victima = serializers.SerializerMethodField()
    tipo_evento = serializers.SerializerMethodField()
    animales = AnimalSerializer(many=True, read_only=True)
    denuncias = DenunciaSerializer(many=True, read_only=True)
    documentos = serializers.SerializerMethodField()
    seguimientos = serializers.SerializerMethodField()
    marcas = serializers.ListField(child=serializers.CharField(), read_only=True)
    completitud = serializers.SerializerMethodField()
    coincidencias = serializers.SerializerMethodField()

    class Meta:
        model = Caso
        fields = [
            'id', 'estado', 'motivo_espera', 'motivo_desestimacion', 'unificado_en', 'origen', 'registrado_por',
            'creado_en', 'actualizado_en', 'victima', 'tipo_evento', 'fecha_hecho', 'lugar_direccion',
            'lugar_ciudad', 'latitud', 'longitud', 'tipo_lugar', 'situacion_persona', 'lesion',
            'lesion_localizacion', 'lesion_gravedad', 'atencion_medica', 'hizo_denuncia', 'motivo_no_denuncia',
            'observaciones', 'animales', 'denuncias', 'documentos', 'seguimientos', 'marcas', 'completitud',
            'coincidencias',
        ]

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        if ocultar_datos(self.context):
            datos['lugar_direccion'] = ''
            datos['observaciones'] = ''
            datos['motivo_no_denuncia'] = ''
            # Ubicación aproximada (~1 km): sirve para análisis geográfico sin señalar un domicilio.
            for campo in ('latitud', 'longitud'):
                if datos[campo] is not None:
                    datos[campo] = round(float(datos[campo]), 2)
        return datos

    def get_registrado_por(self, obj) -> str:
        return obj.registrado_por.nombre_completo

    def get_unificado_en(self, obj) -> str | None:
        return obj.unificado_en.numero if obj.unificado_en_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_victima(self, obj):
        datos = dict(PersonaSerializer(obj.victima, context=self.context).data)
        datos['edad'] = obj.victima.edad_al(obj.fecha_hecho)
        return datos

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_tipo_evento(self, obj):
        return {'id': obj.tipo_evento_id, 'nombre': obj.tipo_evento.nombre} if obj.tipo_evento_id else None

    @extend_schema_field(DocumentoSerializer(many=True))
    def get_documentos(self, obj):
        if ocultar_datos(self.context):
            return []
        return DocumentoSerializer(obj.documentos.all(), many=True, context=self.context).data

    @extend_schema_field(SeguimientoSerializer(many=True))
    def get_seguimientos(self, obj):
        if ocultar_datos(self.context):
            return []
        return SeguimientoSerializer(obj.seguimientos.all(), many=True, context=self.context).data

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_completitud(self, obj):
        return completitud(obj, animales=list(obj.animales.all()), n_denuncias=len(obj.denuncias.all()))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_coincidencias(self, obj):
        pares = (
            Coincidencia.objects.filter(Q(caso_a=obj) | Q(caso_b=obj))
            .exclude(estado=Coincidencia.Estado.DESCARTADA)
            .select_related('caso_a', 'caso_b')
        )
        return [
            {
                'id': c.pk, 'tipo': c.tipo, 'estado': c.estado, 'puntaje': c.puntaje,
                'otro_caso': c.otro(obj).numero,
            }
            for c in pares
        ]


# --- Caso: alta y modificación -------------------------------------------------------------------------------------
class CasoEscrituraSerializer(serializers.ModelSerializer):
    victima = PersonaSerializer()
    animales = AnimalSerializer(many=True, required=False)
    denuncias = DenunciaSerializer(many=True, required=False)
    confirmar_duplicado = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Caso
        fields = [
            'victima', 'tipo_evento', 'fecha_hecho', 'lugar_direccion', 'lugar_ciudad', 'latitud', 'longitud',
            'tipo_lugar', 'situacion_persona', 'lesion', 'lesion_localizacion', 'lesion_gravedad',
            'atencion_medica', 'hizo_denuncia', 'motivo_no_denuncia', 'observaciones', 'animales', 'denuncias',
            'confirmar_duplicado',
        ]

    def validate_fecha_hecho(self, valor):
        if valor and valor > timezone.now():
            raise serializers.ValidationError('La fecha del hecho no puede ser futura.')
        return valor

    def validate_tipo_evento(self, tipo):
        if tipo is not None and not tipo.activo:
            raise serializers.ValidationError('Este tipo de evento ya no está disponible.')
        return tipo

    def validate(self, attrs):
        victima = attrs.get('victima')
        if self.instance is None:
            if not victima or not victima.get('dni'):
                raise serializers.ValidationError({'victima': {'dni': ['El DNI de la víctima es obligatorio.']}})
        elif victima is not None and 'dni' in victima and not victima['dni']:
            raise serializers.ValidationError({'victima': {'dni': ['El DNI de la víctima es obligatorio.']}})
        return attrs


class CambioEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=[e for e in Estado.choices if e[0] != Estado.UNIFICADO])
    motivo_espera = serializers.ChoiceField(choices=MotivoEspera.choices, required=False, allow_blank=True, default='')
    motivo = serializers.CharField(required=False, allow_blank=True, default='')


class DesestimarSerializer(serializers.Serializer):
    motivo = serializers.CharField()


# --- Coincidencias ----------------------------------------------------------------------------------------------------
class CoincidenciaSerializer(serializers.ModelSerializer):
    caso_a = CasoListaSerializer(read_only=True)
    caso_b = CasoListaSerializer(read_only=True)

    class Meta:
        model = Coincidencia
        fields = [
            'id', 'tipo', 'estado', 'fuerza', 'puntaje', 'senales', 'nota', 'caso_a', 'caso_b', 'creado_en',
            'resuelta_en',
        ]


class CoincidenciaDetalleSerializer(CoincidenciaSerializer):
    """Dos casos lado a lado, con las señales que los acercan, su peso y las que son «no evaluable»."""

    caso_a = CasoDetalleSerializer(read_only=True)
    caso_b = CasoDetalleSerializer(read_only=True)


class ConsolidarSerializer(serializers.Serializer):
    superviviente = serializers.CharField(required=False, allow_blank=True, default='')
    campos = serializers.DictField(
        child=serializers.ChoiceField(choices=['principal', 'absorbido']), required=False, default=dict
    )
    confirmacion = serializers.BooleanField(default=False)


class DescartarSerializer(serializers.Serializer):
    nota = serializers.CharField(required=False, allow_blank=True, default='')


# --- Catálogos ---------------------------------------------------------------------------------------------------------------
class TipoEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoEvento
        fields = ['id', 'nombre', 'descripcion', 'activo', 'orden']


class EnteDenunciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnteDenuncia
        fields = ['id', 'nombre', 'activo']
