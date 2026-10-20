import os
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .utiles import normalizar, telefono_clave


# --- Valores enumerados --------------------------------------------------------
class Estado(models.TextChoices):
    REGISTRADO = 'registrado', 'Registrado'
    EN_SEGUIMIENTO = 'en_seguimiento', 'En seguimiento'
    FINALIZADO = 'finalizado', 'Finalizado'
    DESESTIMADO = 'desestimado', 'Desestimado'
    UNIFICADO = 'unificado', 'Unificado en otro caso'


ESTADOS_NO_VIGENTES = (Estado.DESESTIMADO, Estado.UNIFICADO)


class MotivoEspera(models.TextChoices):
    CONTACTO = 'contacto', 'Pendiente de contacto'
    RESPUESTA = 'respuesta', 'Pendiente de respuesta'
    CERTIFICADO = 'certificado', 'Pendiente de certificado'


class TriEstado(models.TextChoices):
    """«No sabe» (la persona respondió que no sabe) y «Sin dato» (no se preguntó / no respondió)
    son cosas distintas y nunca se muestran igual."""

    SI = 'si', 'Sí'
    NO = 'no', 'No'
    NO_SABE = 'no_sabe', 'No sabe'
    SIN_DATO = 'sin_dato', 'Sin dato'


# --- Catálogos administrables ----------------------------------------------------
class TipoEvento(models.Model):
    """Clasifica al caso (ataque con mordedura, lesión compatible...). Valores en revisión con el cliente."""

    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'tipo de evento'
        verbose_name_plural = 'tipos de evento'

    def __str__(self):
        return self.nombre


class EnteDenuncia(models.Model):
    """Ente ante el cual se pudo hacer una denuncia (Zoonosis, policía...). Lista por confirmar."""

    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'ente de denuncia'
        verbose_name_plural = 'entes de denuncia'

    def __str__(self):
        return self.nombre


# --- Personas ------------------------------------------------------------------------
class Persona(models.Model):
    """Víctima o denunciante. Se distinguen porque a veces la víctima es menor y denuncia un adulto."""

    class Sexo(models.TextChoices):
        FEMENINO = 'f', 'Femenino'
        MASCULINO = 'm', 'Masculino'
        OTRO = 'x', 'Otro'
        SIN_DATO = 'sin_dato', 'Sin dato'

    nombre = models.CharField(max_length=80, blank=True)
    apellido = models.CharField(max_length=80, blank=True)
    dni = models.CharField(max_length=12, blank=True, db_index=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    edad_declarada = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(120)])
    sexo = models.CharField(max_length=10, choices=Sexo.choices, default=Sexo.SIN_DATO)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)

    # Claves de comparación (R.13). Se calculan solas al guardar.
    telefono_clave = models.CharField(max_length=8, blank=True, db_index=True, editable=False)
    nombre_clave = models.CharField(max_length=160, blank=True, db_index=True, editable=False)

    def save(self, *args, **kwargs):
        self.telefono_clave = telefono_clave(self.telefono)
        self.nombre_clave = normalizar(f'{self.nombre} {self.apellido}')
        super().save(*args, **kwargs)

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'.strip()

    def edad_al(self, fecha=None):
        """Edad a la fecha del hecho (o hoy). Si no hay fecha de nacimiento usa la edad declarada."""
        if self.fecha_nacimiento:
            ref = timezone.localtime(fecha).date() if fecha else timezone.localdate()
            n = self.fecha_nacimiento
            return ref.year - n.year - ((ref.month, ref.day) < (n.month, n.day))
        return self.edad_declarada

    def __str__(self):
        return self.nombre_completo or f'Persona {self.pk}'


# --- Caso -------------------------------------------------------------------------------
class CasoQuerySet(models.QuerySet):
    def vigentes(self):
        """Las listas de trabajo y las estadísticas cuentan solo casos vigentes."""
        return self.exclude(estado__in=ESTADOS_NO_VIGENTES)


class SecuenciaCaso(models.Model):
    """Contador por año para armar C-2026-0418."""

    anio = models.PositiveSmallIntegerField(primary_key=True)
    ultimo = models.PositiveIntegerField(default=0)


class Caso(models.Model):
    class TipoLugar(models.TextChoices):
        VIA_PUBLICA = 'via_publica', 'Vía pública'
        DOMICILIO_VICTIMA = 'domicilio_victima', 'Domicilio de la víctima'
        DOMICILIO_ANIMAL = 'domicilio_animal', 'Domicilio del animal'
        ESTABLECIMIENTO = 'establecimiento', 'Establecimiento / comercio'
        ESPACIO_VERDE = 'espacio_verde', 'Plaza / espacio verde'
        OTRO = 'otro', 'Otro'
        SIN_DATO = 'sin_dato', 'Sin dato'

    class SituacionPersona(models.TextChoices):
        LABORAL = 'laboral', 'Laboral'
        RECREATIVA = 'recreativa', 'Recreativa'
        TRANSITO = 'transito', 'En tránsito / caminando'
        DOMESTICA = 'domestica', 'Doméstica'
        OTRA = 'otra', 'Otra'
        SIN_DATO = 'sin_dato', 'Sin dato'

    class Lesion(models.TextChoices):
        MORDEDURA = 'mordedura', 'Mordedura'
        ARANAZO = 'aranazo', 'Arañazo'
        COMPATIBLE = 'compatible', 'Lesión compatible'
        INTENTO = 'intento', 'Intento de ataque sin lesión'
        SIN_DATO = 'sin_dato', 'Sin dato'

    class Gravedad(models.TextChoices):
        LEVE = 'leve', 'Leve'
        MODERADA = 'moderada', 'Moderada'
        GRAVE = 'grave', 'Grave'
        SIN_DATO = 'sin_dato', 'Sin dato'

    class HizoDenuncia(models.TextChoices):
        SI = 'si', 'Sí'
        NO = 'no', 'No'
        SIN_DATO = 'sin_dato', 'Sin dato'

    numero = models.CharField(max_length=20, unique=True, editable=False)  # C-2026-0418
    anio = models.PositiveSmallIntegerField(editable=False)
    secuencia = models.PositiveIntegerField(editable=False)

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.REGISTRADO, db_index=True)
    motivo_espera = models.CharField(max_length=20, choices=MotivoEspera.choices, blank=True)
    motivo_desestimacion = models.TextField(blank=True)
    unificado_en = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='absorbidos')

    organismo = models.ForeignKey('accounts.Organismo', on_delete=models.PROTECT, related_name='casos')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='casos_registrados'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    victima = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name='casos_como_victima')
    tipo_evento = models.ForeignKey(TipoEvento, null=True, blank=True, on_delete=models.PROTECT, related_name='casos')

    # Hecho y lugar
    fecha_hecho = models.DateTimeField(null=True, blank=True, db_index=True)
    lugar_direccion = models.CharField(max_length=200, blank=True)
    lugar_ciudad = models.CharField(max_length=100, blank=True, db_index=True)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    tipo_lugar = models.CharField(max_length=20, choices=TipoLugar.choices, default=TipoLugar.SIN_DATO)
    situacion_persona = models.CharField(
        max_length=20, choices=SituacionPersona.choices, default=SituacionPersona.SIN_DATO
    )

    # Lesión
    lesion = models.CharField(max_length=20, choices=Lesion.choices, default=Lesion.SIN_DATO)
    lesion_localizacion = models.CharField(max_length=200, blank=True)
    lesion_gravedad = models.CharField(max_length=20, choices=Gravedad.choices, default=Gravedad.SIN_DATO)
    atencion_medica = models.CharField(max_length=10, choices=TriEstado.choices, default=TriEstado.SIN_DATO)

    # Denuncia (las denuncias concretas viven en el modelo Denuncia, dentro del caso)
    hizo_denuncia = models.CharField(max_length=10, choices=HizoDenuncia.choices, default=HizoDenuncia.SIN_DATO)
    motivo_no_denuncia = models.CharField(max_length=255, blank=True)

    observaciones = models.TextField(blank=True)

    # Marcas: se recalculan desde los servicios (apps/casos/servicios/marcas.py)
    incompleto = models.BooleanField(default=False, db_index=True)
    marca_duplicado = models.BooleanField(default=False, db_index=True)
    marca_relacionado = models.BooleanField(default=False, db_index=True)

    objects = CasoQuerySet.as_manager()

    class Meta:
        ordering = ['-anio', '-secuencia']
        constraints = [models.UniqueConstraint(fields=['anio', 'secuencia'], name='caso_anio_secuencia_unica')]

    @property
    def vigente(self):
        return self.estado not in ESTADOS_NO_VIGENTES

    @property
    def marcas(self):
        marcas = []
        if self.incompleto:
            marcas.append('incompleto')
        if self.marca_duplicado:
            marcas.append('duplicado')
        if self.marca_relacionado:
            marcas.append('relacionado')
        return marcas

    def __str__(self):
        return self.numero


class Animal(models.Model):
    class Especie(models.TextChoices):
        PERRO = 'perro', 'Perro'
        GATO = 'gato', 'Gato'
        OTRO = 'otro', 'Otro'

    class Tamano(models.TextChoices):
        CHICO = 'chico', 'Chico'
        MEDIANO = 'mediano', 'Mediano'
        GRANDE = 'grande', 'Grande'
        SIN_DATO = 'sin_dato', 'Sin dato'

    class Tenencia(models.TextChoices):
        PROPIO = 'propio', 'Propio (de la víctima)'
        AJENO = 'ajeno', 'Ajeno (de otra persona)'
        COMUNITARIO = 'comunitario', 'Comunitario'
        ASILVESTRADO = 'asilvestrado', 'Asilvestrado'
        SIN_DATO = 'sin_dato', 'Sin dato'

    caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name='animales')
    especie = models.CharField(max_length=10, choices=Especie.choices, default=Especie.PERRO)
    tamano = models.CharField(max_length=10, choices=Tamano.choices, default=Tamano.SIN_DATO)
    raza = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=80, blank=True)
    nombre = models.CharField(max_length=80, blank=True)
    tenencia = models.CharField(max_length=15, choices=Tenencia.choices, default=Tenencia.SIN_DATO)
    procedencia = models.CharField(max_length=200, blank=True)
    identificacion = models.CharField('chip / identificación', max_length=60, blank=True)
    vacunado = models.CharField('vacunación antirrábica', max_length=10, choices=TriEstado.choices, default=TriEstado.SIN_DATO)
    castrado = models.CharField(max_length=10, choices=TriEstado.choices, default=TriEstado.SIN_DATO)
    antecedentes_ataques = models.CharField(max_length=10, choices=TriEstado.choices, default=TriEstado.SIN_DATO)
    # Tenedor responsable: dato personal, se oculta a quien no corresponde
    tenedor_nombre = models.CharField(max_length=160, blank=True)
    tenedor_telefono = models.CharField(max_length=30, blank=True)
    tenedor_direccion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name_plural = 'animales'

    def __str__(self):
        return f'{self.get_especie_display()} ({self.caso_id})'


class Denuncia(models.Model):
    """Trámite oficial hecho en un ente. Vive dentro de un caso: no tiene pantalla, estados ni identificador propios."""

    caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name='denuncias')
    ente = models.ForeignKey(EnteDenuncia, on_delete=models.PROTECT, related_name='denuncias')
    numero = models.CharField(max_length=60, blank=True)
    fecha = models.DateField(null=True, blank=True)
    realizada_por = models.ForeignKey(
        Persona, null=True, blank=True, on_delete=models.SET_NULL, related_name='denuncias_realizadas'
    )
    vinculo = models.CharField('vínculo con la víctima', max_length=100, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


def ruta_documento(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'documentos/{instance.caso.anio}/{uuid.uuid4().hex}{extension}'


class Documento(models.Model):
    class Tipo(models.TextChoices):
        CERTIFICADO_MEDICO = 'certificado_medico', 'Certificado médico'
        DENUNCIA = 'denuncia', 'Constancia de denuncia'
        FOTO = 'foto', 'Fotografía'
        OTRO = 'otro', 'Otro'

    class EstadoValidacion(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de validación'
        VALIDADO = 'validado', 'Validado'
        RECHAZADO = 'rechazado', 'Rechazado'

    caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name='documentos')
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OTRO)
    archivo = models.FileField(
        upload_to=ruta_documento,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
    )
    nombre_original = models.CharField(max_length=255, blank=True)
    cargado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='documentos_cargados')
    cargado_en = models.DateTimeField(auto_now_add=True)
    estado_validacion = models.CharField(
        max_length=12, choices=EstadoValidacion.choices, default=EstadoValidacion.PENDIENTE
    )
    validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='documentos_validados'
    )
    validado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-cargado_en']


class Seguimiento(models.Model):
    """R.15: acciones realizadas para completar o actualizar el caso hasta su cierre."""

    caso = models.ForeignKey(Caso, on_delete=models.CASCADE, related_name='seguimientos')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='seguimientos')
    descripcion = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']


# --- Coincidencias (posibles duplicados / eventos relacionados) ---------------------------------
class Coincidencia(models.Model):
    class Tipo(models.TextChoices):
        DUPLICADO = 'duplicado', 'Posible duplicado'
        RELACIONADO = 'relacionado', 'Evento relacionado'

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de revisión'
        CONSOLIDADA = 'consolidada', 'Consolidada'
        VINCULADA = 'vinculada', 'Vinculada'
        DESCARTADA = 'descartada', 'Descartada'

    # Siempre caso_a.pk < caso_b.pk: un par se guarda una sola vez.
    caso_a = models.ForeignKey(Caso, on_delete=models.PROTECT, related_name='coincidencias_como_a')
    caso_b = models.ForeignKey(Caso, on_delete=models.PROTECT, related_name='coincidencias_como_b')
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    fuerza = models.CharField(max_length=10, default='debil')  # 'fuerte' = mismo DNI o teléfono
    puntaje = models.PositiveSmallIntegerField(default=0)
    senales = models.JSONField(default=list)
    nota = models.CharField(max_length=255, blank=True)
    caso_superviviente = models.ForeignKey(
        Caso, null=True, blank=True, on_delete=models.PROTECT, related_name='coincidencias_sobrevividas'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='coincidencias_resueltas'
    )
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-puntaje', '-creado_en']
        constraints = [
            models.UniqueConstraint(fields=['caso_a', 'caso_b'], name='coincidencia_par_unico'),
            models.CheckConstraint(condition=models.Q(caso_a__lt=models.F('caso_b')), name='coincidencia_orden_par'),
        ]

    def otro(self, caso):
        return self.caso_b if caso.pk == self.caso_a_id else self.caso_a


# --- Auditoría (R.29) -----------------------------------------------------------------------------
class EventoAuditoria(models.Model):
    """Quién hizo qué y cuándo. Solo se agrega: no se edita ni se borra. `usuario` nulo = «Sistema»."""

    class Accion(models.TextChoices):
        CREADO = 'creado', 'Caso registrado'
        EDITADO = 'editado', 'Datos modificados'
        ESTADO = 'estado', 'Cambio de estado'
        ANIMAL = 'animal', 'Animal agregado o modificado'
        DENUNCIA = 'denuncia', 'Denuncia anotada o modificada'
        DOCUMENTO = 'documento', 'Documento incorporado o validado'
        DOCUMENTO_DESCARGADO = 'documento_descargado', 'Documento descargado'
        SEGUIMIENTO = 'seguimiento', 'Seguimiento registrado'
        COINCIDENCIA = 'coincidencia', 'Coincidencia detectada'
        CONSOLIDADO = 'consolidado', 'Casos consolidados'
        VINCULADO = 'vinculado', 'Casos vinculados'
        DESCARTADO = 'descartado', 'Coincidencia descartada'
        DESVINCULADO = 'desvinculado', 'Vínculo deshecho'

    caso = models.ForeignKey(Caso, on_delete=models.PROTECT, related_name='auditoria')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='eventos_auditoria'
    )
    accion = models.CharField(max_length=25, choices=Accion.choices)
    detalle = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en', 'id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Los eventos de auditoría no se pueden modificar.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Los eventos de auditoría no se pueden borrar.')
