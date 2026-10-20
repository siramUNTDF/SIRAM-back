"""Operaciones sobre casos (R.11, R.12, R.15). Todo cambio deja constancia en la auditoría."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import (
    Animal,
    Caso,
    Denuncia,
    Documento,
    Estado,
    EventoAuditoria,
    MotivoEspera,
    Persona,
    Seguimiento,
)
from . import auditoria
from .coincidencias import detectar_coincidencias
from .excepciones import PosibleDuplicado
from .marcas import refrescar_marcas
from .numeracion import siguiente_numero

Accion = EventoAuditoria.Accion


# --- Alta y modificación -------------------------------------------------------------------------
@transaction.atomic
def crear_caso(usuario, datos, confirmar_duplicado=False):
    """Registra un caso nuevo con su víctima, animales y denuncias.

    Si hay un caso muy parecido (mismo DNI o teléfono) y no se confirmó, lanza PosibleDuplicado:
    la transacción se revierte y no se crea nada."""
    datos = dict(datos)
    victima_datos = dict(datos.pop('victima'))
    animales = datos.pop('animales', [])
    denuncias = datos.pop('denuncias', [])

    victima = Persona.objects.create(**victima_datos)
    anio, secuencia, numero = siguiente_numero()
    caso = Caso.objects.create(
        numero=numero, anio=anio, secuencia=secuencia,
        organismo=usuario.organismo, registrado_por=usuario, victima=victima, **datos,
    )
    for animal in animales:
        Animal.objects.create(caso=caso, **animal)
    for denuncia in denuncias:
        _crear_denuncia(caso, denuncia)

    auditoria.registrar(caso, usuario, Accion.CREADO, {'organismo': usuario.organismo.nombre})
    hallazgos = detectar_coincidencias(caso)

    fuertes = [h for h in hallazgos if h.tipo == 'duplicado' and h.fuerza == 'fuerte']
    if fuertes and not confirmar_duplicado:
        raise PosibleDuplicado(fuertes)
    return caso


@transaction.atomic
def actualizar_caso(usuario, caso, datos):
    if caso.estado == Estado.UNIFICADO:
        raise ValidationError({'detalle': 'Un caso unificado no se puede editar: los datos están en el caso que lo absorbió.'})
    datos = dict(datos)
    victima_datos = datos.pop('victima', None)
    datos.pop('animales', None)
    datos.pop('denuncias', None)

    antes = auditoria.instantanea(caso)
    for campo, valor in datos.items():
        setattr(caso, campo, valor)
    caso.save()
    if victima_datos:
        for campo, valor in victima_datos.items():
            setattr(caso.victima, campo, valor)
        caso.victima.save()

    cambios = auditoria.diferencias(antes, auditoria.instantanea(caso))
    if cambios:
        auditoria.registrar(caso, usuario, Accion.EDITADO, {'cambios': cambios})
    detectar_coincidencias(caso)
    return caso


# --- Estado (R.15) -------------------------------------------------------------------------------
TRANSICIONES = {
    Estado.REGISTRADO: {Estado.EN_SEGUIMIENTO, Estado.FINALIZADO, Estado.DESESTIMADO},
    Estado.EN_SEGUIMIENTO: {Estado.EN_SEGUIMIENTO, Estado.FINALIZADO, Estado.DESESTIMADO},
    Estado.FINALIZADO: {Estado.EN_SEGUIMIENTO},
    Estado.DESESTIMADO: {Estado.REGISTRADO},
    Estado.UNIFICADO: set(),
}


@transaction.atomic
def cambiar_estado(usuario, caso, nuevo, motivo_espera='', motivo=''):
    """Cambia el estado del caso. Desestimar es la única forma de «dar de baja»: no se borra nada."""
    actual = caso.estado
    if actual == Estado.UNIFICADO:
        raise ValidationError({'estado': 'Un caso unificado no cambia de estado.'})
    if nuevo == Estado.UNIFICADO:
        raise ValidationError({'estado': 'Un caso solo pasa a «Unificado» al consolidar una coincidencia.'})
    if nuevo not in TRANSICIONES[actual]:
        raise ValidationError({'estado': f'No se puede pasar de «{actual}» a «{nuevo}».'})
    if nuevo == Estado.EN_SEGUIMIENTO and motivo_espera not in MotivoEspera.values:
        raise ValidationError({'motivo_espera': 'Al pasar a «En seguimiento» hay que elegir el motivo de espera.'})
    motivo = (motivo or '').strip()
    if nuevo == Estado.DESESTIMADO and not motivo:
        raise ValidationError({'motivo': 'Para desestimar un caso el motivo es obligatorio.'})

    caso.estado = nuevo
    caso.motivo_espera = motivo_espera if nuevo == Estado.EN_SEGUIMIENTO else ''
    caso.motivo_desestimacion = motivo if nuevo == Estado.DESESTIMADO else ''
    caso.save(update_fields=['estado', 'motivo_espera', 'motivo_desestimacion', 'actualizado_en'])

    detalle = {'de': actual, 'a': nuevo}
    if caso.motivo_espera:
        detalle['motivo_espera'] = caso.motivo_espera
    if nuevo == Estado.DESESTIMADO:
        detalle['motivo'] = motivo
    auditoria.registrar(caso, usuario, Accion.ESTADO, detalle)

    # Un caso que vuelve a estar vigente se vuelve a comparar; uno que sale de vigencia limpia sus marcas.
    detectar_coincidencias(caso) if caso.vigente else refrescar_marcas(caso)
    return caso


# --- Animales, denuncias, documentos, seguimientos -------------------------------------------------
def _reevaluar(caso):
    detectar_coincidencias(caso)


@transaction.atomic
def agregar_animal(usuario, caso, datos):
    animal = Animal.objects.create(caso=caso, **datos)
    auditoria.registrar(caso, usuario, Accion.ANIMAL, {'animal': animal.pk, 'operacion': 'alta'})
    _reevaluar(caso)
    return animal


@transaction.atomic
def actualizar_animal(usuario, animal, datos):
    for campo, valor in datos.items():
        setattr(animal, campo, valor)
    animal.save()
    auditoria.registrar(animal.caso, usuario, Accion.ANIMAL, {'animal': animal.pk, 'operacion': 'modificacion'})
    _reevaluar(animal.caso)
    return animal


def _crear_denuncia(caso, datos):
    datos = dict(datos)
    denunciante = datos.pop('realizada_por', None)
    if denunciante:
        datos['realizada_por'] = Persona.objects.create(**denunciante)
    return Denuncia.objects.create(caso=caso, **datos)


@transaction.atomic
def agregar_denuncia(usuario, caso, datos):
    denuncia = _crear_denuncia(caso, datos)
    if caso.hizo_denuncia != Caso.HizoDenuncia.SI:
        caso.hizo_denuncia = Caso.HizoDenuncia.SI
        caso.save(update_fields=['hizo_denuncia', 'actualizado_en'])
    auditoria.registrar(
        caso, usuario, Accion.DENUNCIA, {'denuncia': denuncia.pk, 'ente': denuncia.ente.nombre, 'operacion': 'alta'}
    )
    refrescar_marcas(caso, propagar=False)
    return denuncia


@transaction.atomic
def actualizar_denuncia(usuario, denuncia, datos):
    datos = dict(datos)
    denunciante = datos.pop('realizada_por', None)
    for campo, valor in datos.items():
        setattr(denuncia, campo, valor)
    if denunciante:
        if denuncia.realizada_por_id:
            for campo, valor in denunciante.items():
                setattr(denuncia.realizada_por, campo, valor)
            denuncia.realizada_por.save()
        else:
            denuncia.realizada_por = Persona.objects.create(**denunciante)
    denuncia.save()
    auditoria.registrar(
        denuncia.caso, usuario, Accion.DENUNCIA, {'denuncia': denuncia.pk, 'operacion': 'modificacion'}
    )
    return denuncia


@transaction.atomic
def agregar_documento(usuario, caso, tipo, archivo):
    documento = Documento.objects.create(
        caso=caso, tipo=tipo, archivo=archivo, nombre_original=getattr(archivo, 'name', '')[:255], cargado_por=usuario
    )
    auditoria.registrar(caso, usuario, Accion.DOCUMENTO, {'documento': documento.pk, 'tipo': tipo, 'operacion': 'alta'})
    return documento


@transaction.atomic
def validar_documento(usuario, documento, estado_validacion):
    documento.estado_validacion = estado_validacion
    documento.validado_por = usuario
    documento.validado_en = timezone.now()
    documento.save(update_fields=['estado_validacion', 'validado_por', 'validado_en'])
    auditoria.registrar(
        documento.caso, usuario, Accion.DOCUMENTO,
        {'documento': documento.pk, 'operacion': 'validacion', 'resultado': estado_validacion},
    )
    return documento


@transaction.atomic
def agregar_seguimiento(usuario, caso, descripcion):
    seguimiento = Seguimiento.objects.create(caso=caso, usuario=usuario, descripcion=descripcion)
    auditoria.registrar(caso, usuario, Accion.SEGUIMIENTO, {'seguimiento': seguimiento.pk})
    return seguimiento
