"""Resolución de coincidencias: consolidar (irreversible), vincular (reversible) y descartar.

Reglas de la narrativa:
- Consolidar funde dos casos que son el MISMO incidente. Se elige campo por campo qué valor sobrevive;
  si un caso tiene el dato y el otro no, se conserva el que lo tiene. Exige confirmación explícita.
  El caso absorbido queda «Unificado» y apunta al que sobrevive; sus datos originales se conservan.
- Un evento relacionado (dos víctimas del mismo animal) NUNCA se consolida: borraría una víctima de las estadísticas.
- Vincular enlaza sin fundir y se puede deshacer. Descartar quita la marca.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import Animal, Caso, Coincidencia, Estado, EventoAuditoria
from . import auditoria
from .coincidencias import COINCIDE, animales_equivalentes, detectar_coincidencias
from .marcas import refrescar_marcas

Accion = EventoAuditoria.Accion

CAMPOS_DEL_CASO = [c for c in auditoria.CAMPOS_CASO if c not in ('latitud', 'longitud')] + ['coordenadas']
CAMPOS_DE_LA_VICTIMA = [f'victima.{c}' for c in auditoria.CAMPOS_PERSONA]
CAMPOS_CONSOLIDABLES = CAMPOS_DEL_CASO + CAMPOS_DE_LA_VICTIMA


def _vacio(valor):
    return valor is None or valor == '' or valor == 'sin_dato'


def _leer(caso, campo):
    if campo == 'coordenadas':
        return (caso.latitud, caso.longitud)
    if campo.startswith('victima.'):
        return getattr(caso.victima, campo.split('.', 1)[1])
    return getattr(caso, campo)


def _escribir(caso, campo, valor):
    if campo == 'coordenadas':
        caso.latitud, caso.longitud = valor
    elif campo.startswith('victima.'):
        setattr(caso.victima, campo.split('.', 1)[1], valor)
    else:
        setattr(caso, campo, valor)


def _es_vacio_campo(valor):
    if isinstance(valor, tuple):
        return any(v is None for v in valor)
    return _vacio(valor)


def _resolver_pendiente(coincidencia, usuario, nuevo_estado):
    if coincidencia.estado != Coincidencia.Estado.PENDIENTE:
        raise ValidationError({'detalle': 'Esta coincidencia ya fue resuelta.'})
    coincidencia.estado = nuevo_estado
    coincidencia.resuelta_por = usuario
    coincidencia.resuelta_en = timezone.now()


@transaction.atomic
def consolidar(coincidencia, usuario, superviviente=None, campos=None, confirmacion=False):
    if coincidencia.tipo != Coincidencia.Tipo.DUPLICADO:
        raise ValidationError({'detalle': 'Los eventos relacionados no se consolidan: se vinculan.'})
    if coincidencia.estado != Coincidencia.Estado.PENDIENTE:
        raise ValidationError({'detalle': 'Esta coincidencia ya fue resuelta.'})
    if not confirmacion:
        raise ValidationError({'confirmacion': 'Hay que confirmar explícitamente que son la misma persona y el mismo incidente.'})

    campos = dict(campos or {})
    invalidos = [c for c in campos if c not in CAMPOS_CONSOLIDABLES]
    if invalidos:
        raise ValidationError({'campos': f'Campos desconocidos: {", ".join(invalidos)}.'})
    if any(v not in ('principal', 'absorbido') for v in campos.values()):
        raise ValidationError({'campos': 'Cada campo debe indicar «principal» o «absorbido».'})

    # Se bloquean ambas filas para que dos agentes no consoliden a la vez.
    bloqueados = {c.pk: c for c in Caso.objects.select_for_update().select_related('victima').filter(
        pk__in=[coincidencia.caso_a_id, coincidencia.caso_b_id]
    )}
    caso_a, caso_b = bloqueados[coincidencia.caso_a_id], bloqueados[coincidencia.caso_b_id]
    if not (caso_a.vigente and caso_b.vigente):
        raise ValidationError({'detalle': 'Solo se pueden consolidar casos vigentes.'})

    if superviviente in (None, '', caso_a.numero):
        principal, absorbido = caso_a, caso_b
    elif superviviente == caso_b.numero:
        principal, absorbido = caso_b, caso_a
    else:
        raise ValidationError({'superviviente': 'El caso que sobrevive debe ser uno de los dos de la coincidencia.'})

    foto_absorbido = auditoria.instantanea_enmascarada(absorbido)

    # Campo por campo: lo que se elige a mano manda; si no, gana el principal salvo que le falte el dato.
    elegidos = {}
    for campo in CAMPOS_CONSOLIDABLES:
        valor_principal, valor_absorbido = _leer(principal, campo), _leer(absorbido, campo)
        decision = campos.get(campo)
        if decision is None:
            decision = 'absorbido' if _es_vacio_campo(valor_principal) and not _es_vacio_campo(valor_absorbido) else 'principal'
        if decision == 'absorbido' and valor_absorbido != valor_principal:
            _escribir(principal, campo, valor_absorbido)
            elegidos[campo] = 'absorbido'
    principal.victima.save()
    principal.save()

    # Lo que cuelga del caso absorbido pasa al principal, evitando repetir lo que ya está.
    animales_principal = list(Animal.objects.filter(caso=principal))
    animales_movidos = []
    for animal in Animal.objects.filter(caso=absorbido):
        if any(animales_equivalentes(animal, otro) == COINCIDE for otro in animales_principal):
            continue
        animal.caso = principal
        animal.save(update_fields=['caso'])
        animales_movidos.append(animal.pk)

    denuncias_movidas = []
    existentes = {(d.ente_id, d.numero) for d in principal.denuncias.all()}
    for denuncia in absorbido.denuncias.all():
        if denuncia.numero and (denuncia.ente_id, denuncia.numero) in existentes:
            continue
        denuncia.caso = principal
        denuncia.save(update_fields=['caso'])
        denuncias_movidas.append(denuncia.pk)

    documentos_movidos = list(absorbido.documentos.values_list('pk', flat=True))
    absorbido.documentos.update(caso=principal)
    absorbido.seguimientos.update(caso=principal)

    if principal.hizo_denuncia == Caso.HizoDenuncia.SIN_DATO and principal.denuncias.exists():
        principal.hizo_denuncia = Caso.HizoDenuncia.SI
        principal.save(update_fields=['hizo_denuncia', 'actualizado_en'])

    absorbido.estado = Estado.UNIFICADO
    absorbido.unificado_en = principal
    absorbido.motivo_espera = ''
    absorbido.save(update_fields=['estado', 'unificado_en', 'motivo_espera', 'actualizado_en'])

    _resolver_pendiente(coincidencia, usuario, Coincidencia.Estado.CONSOLIDADA)
    coincidencia.caso_superviviente = principal
    coincidencia.save(update_fields=['estado', 'caso_superviviente', 'resuelta_por', 'resuelta_en'])

    # Las demás sospechas del caso absorbido ya no tienen objeto.
    for otra in Coincidencia.objects.filter(
        Q(caso_a=absorbido) | Q(caso_b=absorbido), estado=Coincidencia.Estado.PENDIENTE
    ):
        otra.estado = Coincidencia.Estado.DESCARTADA
        otra.nota = f'El caso {absorbido.numero} fue absorbido por {principal.numero}.'
        otra.resuelta_por = usuario
        otra.resuelta_en = timezone.now()
        otra.save(update_fields=['estado', 'nota', 'resuelta_por', 'resuelta_en'])

    detalle = {
        'principal': principal.numero,
        'absorbido': absorbido.numero,
        'campos_tomados_del_absorbido': sorted(elegidos),
        'animales_movidos': animales_movidos,
        'denuncias_movidas': denuncias_movidas,
        'documentos_movidos': documentos_movidos,
    }
    auditoria.registrar(principal, usuario, Accion.CONSOLIDADO, detalle)
    auditoria.registrar(absorbido, usuario, Accion.CONSOLIDADO, {**detalle, 'datos_originales': foto_absorbido})

    refrescar_marcas(absorbido)
    detectar_coincidencias(principal)  # con los datos ya completos pueden aparecer otras coincidencias
    return principal


@transaction.atomic
def vincular(coincidencia, usuario):
    if coincidencia.tipo != Coincidencia.Tipo.RELACIONADO:
        raise ValidationError({'detalle': 'Solo los eventos relacionados se vinculan; los duplicados se consolidan o se descartan.'})
    _resolver_pendiente(coincidencia, usuario, Coincidencia.Estado.VINCULADA)
    coincidencia.save(update_fields=['estado', 'resuelta_por', 'resuelta_en'])
    for caso, otro in ((coincidencia.caso_a, coincidencia.caso_b), (coincidencia.caso_b, coincidencia.caso_a)):
        auditoria.registrar(caso, usuario, Accion.VINCULADO, {'con': otro.numero})
        refrescar_marcas(caso, propagar=False)
    return coincidencia


@transaction.atomic
def desvincular(coincidencia, usuario):
    if coincidencia.estado != Coincidencia.Estado.VINCULADA:
        raise ValidationError({'detalle': 'Esta coincidencia no está vinculada.'})
    coincidencia.estado = Coincidencia.Estado.PENDIENTE
    coincidencia.resuelta_por = None
    coincidencia.resuelta_en = None
    coincidencia.save(update_fields=['estado', 'resuelta_por', 'resuelta_en'])
    for caso, otro in ((coincidencia.caso_a, coincidencia.caso_b), (coincidencia.caso_b, coincidencia.caso_a)):
        auditoria.registrar(caso, usuario, Accion.DESVINCULADO, {'con': otro.numero})
        refrescar_marcas(caso, propagar=False)
    return coincidencia


@transaction.atomic
def descartar(coincidencia, usuario, nota=''):
    _resolver_pendiente(coincidencia, usuario, Coincidencia.Estado.DESCARTADA)
    coincidencia.nota = (nota or '')[:255]
    coincidencia.save(update_fields=['estado', 'nota', 'resuelta_por', 'resuelta_en'])
    for caso, otro in ((coincidencia.caso_a, coincidencia.caso_b), (coincidencia.caso_b, coincidencia.caso_a)):
        auditoria.registrar(caso, usuario, Accion.DESCARTADO, {'con': otro.numero, 'nota': coincidencia.nota})
        refrescar_marcas(caso, propagar=False)
    return coincidencia
