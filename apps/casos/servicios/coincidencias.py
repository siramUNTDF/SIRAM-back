"""R.13: detección de posibles duplicados y eventos relacionados.

- Posible duplicado: mismo incidente con la misma persona.
    · fuerte: mismo DNI (o mismo teléfono si falta el DNI), dentro de la ventana de días.
    · débil:  mismo nombre y además mismo lugar o misma fecha.
- Evento relacionado: personas distintas, mismo animal, mismo lugar y misma fecha.
  NO es un duplicado y nunca se consolida.

Cada señal puede ser «coincide», «no_coincide» o «no_evaluable» (falta el dato en alguno de los casos).
«No evaluable» no es lo mismo que «no coincide». Nunca hay fusión automática: solo se marca para revisar.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..models import Animal, Caso, Coincidencia, EventoAuditoria
from ..utiles import distancia_metros, normalizar
from . import auditoria
from .marcas import refrescar_marcas

COINCIDE, NO_COINCIDE, NO_EVALUABLE = 'coincide', 'no_coincide', 'no_evaluable'

PESOS = {'dni': 40, 'telefono': 30, 'nombre': 15, 'fecha': 10, 'lugar': 15, 'animal': 20}
ETIQUETAS = {
    'dni': 'Mismo DNI',
    'telefono': 'Mismo teléfono',
    'nombre': 'Mismo nombre',
    'fecha': 'Misma fecha del hecho',
    'lugar': 'Mismo lugar',
    'animal': 'Mismo animal',
}
DISTANCIA_MISMO_LUGAR_M = 150


@dataclass
class Evaluacion:
    tipo: str
    fuerza: str
    puntaje: int
    senales: list


@dataclass
class Hallazgo:
    otro: Caso
    coincidencia: Coincidencia
    tipo: str
    fuerza: str
    puntaje: int
    senales: list


def _comparar(a, b):
    if not a or not b:
        return NO_EVALUABLE
    return COINCIDE if a == b else NO_COINCIDE


def _senal_fecha(a, b):
    if a.fecha_hecho is None or b.fecha_hecho is None:
        return NO_EVALUABLE
    return COINCIDE if abs(a.fecha_hecho - b.fecha_hecho) <= timedelta(hours=24) else NO_COINCIDE


def _senal_lugar(a, b):
    if None not in (a.latitud, a.longitud, b.latitud, b.longitud):
        cerca = distancia_metros(a.latitud, a.longitud, b.latitud, b.longitud) <= DISTANCIA_MISMO_LUGAR_M
        return COINCIDE if cerca else NO_COINCIDE
    da, db = normalizar(a.lugar_direccion), normalizar(b.lugar_direccion)
    ca, cb = normalizar(a.lugar_ciudad), normalizar(b.lugar_ciudad)
    if da and db and ca and cb:
        return COINCIDE if (da == db and ca == cb) else NO_COINCIDE
    return NO_EVALUABLE


def animales_equivalentes(x, y):
    """Dos registros de animal que parecen el mismo ejemplar. Devuelve COINCIDE, NO_COINCIDE o NO_EVALUABLE."""
    chip_x, chip_y = normalizar(x.identificacion), normalizar(y.identificacion)
    if chip_x and chip_y:
        return COINCIDE if chip_x == chip_y else NO_COINCIDE
    if x.especie != y.especie:
        return NO_COINCIDE
    solidas = 0
    for valor_x, valor_y, vacio in (
        (x.tamano, y.tamano, 'sin_dato'),
        (normalizar(x.color), normalizar(y.color), ''),
        (normalizar(x.raza), normalizar(y.raza), ''),
    ):
        if valor_x == vacio or valor_y == vacio:
            continue
        if valor_x != valor_y:
            return NO_COINCIDE
        solidas += 1
    return COINCIDE if solidas else NO_EVALUABLE


def _senal_animal(animales_a, animales_b):
    if not animales_a or not animales_b:
        return NO_EVALUABLE
    resultados = {animales_equivalentes(x, y) for x in animales_a for y in animales_b}
    if COINCIDE in resultados:
        return COINCIDE
    return NO_EVALUABLE if NO_EVALUABLE in resultados else NO_COINCIDE


def evaluar_par(a, b, animales_a=None, animales_b=None):
    """Compara dos casos. Devuelve una Evaluacion, o None si no hay motivo para relacionarlos."""
    animales_a = list(a.animales.all()) if animales_a is None else animales_a
    animales_b = list(b.animales.all()) if animales_b is None else animales_b
    va, vb = a.victima, b.victima

    resultado = {
        'dni': _comparar(va.dni, vb.dni),
        'telefono': _comparar(va.telefono_clave, vb.telefono_clave),
        'nombre': _comparar(va.nombre_clave, vb.nombre_clave),
        'fecha': _senal_fecha(a, b),
        'lugar': _senal_lugar(a, b),
        'animal': _senal_animal(animales_a, animales_b),
    }

    # ¿Es la misma persona?
    if resultado['dni'] == COINCIDE:
        persona = 'fuerte'
    elif resultado['dni'] == NO_EVALUABLE and resultado['telefono'] == COINCIDE:
        persona = 'fuerte'
    elif resultado['dni'] == NO_COINCIDE and resultado['telefono'] == COINCIDE and resultado['nombre'] == COINCIDE:
        persona = 'debil'  # posible error de tipeo en el DNI
    elif resultado['dni'] != NO_COINCIDE and resultado['nombre'] == COINCIDE and COINCIDE in (
        resultado['lugar'], resultado['fecha']
    ):
        persona = 'debil'
    else:
        persona = 'distinta'

    ventana = timedelta(days=getattr(settings, 'SIRAM_VENTANA_DUPLICADOS_DIAS', 7))
    dentro_de_ventana = (
        a.fecha_hecho is None or b.fecha_hecho is None or abs(a.fecha_hecho - b.fecha_hecho) <= ventana
    )

    if persona in ('fuerte', 'debil') and dentro_de_ventana:
        tipo, fuerza = Coincidencia.Tipo.DUPLICADO, ('fuerte' if persona == 'fuerte' else 'debil')
    elif (
        persona == 'distinta'
        and resultado['lugar'] == COINCIDE
        and resultado['fecha'] == COINCIDE
        and resultado['animal'] == COINCIDE
    ):
        tipo, fuerza = Coincidencia.Tipo.RELACIONADO, 'debil'
    else:
        return None

    senales = [
        {'clave': c, 'etiqueta': ETIQUETAS[c], 'peso': PESOS[c], 'resultado': resultado[c]} for c in PESOS
    ]
    puntaje = min(100, sum(PESOS[c] for c in PESOS if resultado[c] == COINCIDE))
    return Evaluacion(tipo=tipo, fuerza=fuerza, puntaje=puntaje, senales=senales)


def candidatos(caso):
    """Casos vigentes que vale la pena comparar con `caso` (se filtra en la base, no en memoria)."""
    v = caso.victima
    filtro = Q()
    if v.dni:
        filtro |= Q(victima__dni=v.dni)
    if v.telefono_clave:
        filtro |= Q(victima__telefono_clave=v.telefono_clave)
    if v.nombre_clave:
        filtro |= Q(victima__nombre_clave=v.nombre_clave)
    if caso.fecha_hecho:
        un_dia = timedelta(days=1)
        filtro |= Q(fecha_hecho__range=(caso.fecha_hecho - un_dia, caso.fecha_hecho + un_dia))
    if not filtro:
        return Caso.objects.none()
    return (
        Caso.objects.vigentes()
        .exclude(pk=caso.pk)
        .filter(filtro)
        .select_related('victima')
        .prefetch_related('animales')
        .distinct()
    )


def detectar_coincidencias(caso):
    """Compara `caso` con los demás, crea/actualiza las coincidencias pendientes y refresca las marcas.
    Devuelve los hallazgos pendientes de revisión (lista de Hallazgo)."""
    hallazgos = []
    if not caso.vigente:
        refrescar_marcas(caso)
        return hallazgos

    caso_animales = list(Animal.objects.filter(caso_id=caso.pk))  # sin caché: puede haber cambiado
    vistas = set()
    for otro in candidatos(caso):
        evaluacion = evaluar_par(caso, otro, caso_animales, list(otro.animales.all()))
        if evaluacion is None:
            continue
        a, b = (caso, otro) if caso.pk < otro.pk else (otro, caso)
        coincidencia, creada = Coincidencia.objects.get_or_create(
            caso_a=a,
            caso_b=b,
            defaults={
                'tipo': evaluacion.tipo,
                'fuerza': evaluacion.fuerza,
                'puntaje': evaluacion.puntaje,
                'senales': evaluacion.senales,
            },
        )
        vistas.add(coincidencia.pk)
        if creada:
            for este, el_otro in ((caso, otro), (otro, caso)):
                auditoria.registrar(
                    este, None, EventoAuditoria.Accion.COINCIDENCIA,
                    {'con': el_otro.numero, 'tipo': evaluacion.tipo, 'puntaje': evaluacion.puntaje},
                )
        elif coincidencia.estado == Coincidencia.Estado.PENDIENTE:
            coincidencia.tipo = evaluacion.tipo
            coincidencia.fuerza = evaluacion.fuerza
            coincidencia.puntaje = evaluacion.puntaje
            coincidencia.senales = evaluacion.senales
            coincidencia.save(update_fields=['tipo', 'fuerza', 'puntaje', 'senales'])
        if coincidencia.estado == Coincidencia.Estado.PENDIENTE:
            hallazgos.append(
                Hallazgo(otro, coincidencia, evaluacion.tipo, evaluacion.fuerza, evaluacion.puntaje, evaluacion.senales)
            )

    # Pendientes que dejaron de coincidir tras una edición: se cierran solas, dejando constancia.
    obsoletas = (
        Coincidencia.objects.filter(Q(caso_a=caso) | Q(caso_b=caso), estado=Coincidencia.Estado.PENDIENTE)
        .exclude(pk__in=vistas)
    )
    for coincidencia in obsoletas:
        coincidencia.estado = Coincidencia.Estado.DESCARTADA
        coincidencia.nota = 'Dejó de coincidir tras una modificación de los datos.'
        coincidencia.resuelta_en = timezone.now()
        coincidencia.save(update_fields=['estado', 'nota', 'resuelta_en'])

    refrescar_marcas(caso)  # también refresca a los pares
    return hallazgos
