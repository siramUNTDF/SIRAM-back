"""Marcas del caso (Incompleto · Posible duplicado · Posible evento relacionado).

Se guardan como booleanos en el caso para poder filtrar y contar rápido (menú, bandeja, inicio).
Reglas de la narrativa: las marcas de duplicado/relacionado solo existen en casos vigentes
(un caso unificado o desestimado ya no tiene nada por hacer) y solo mientras la coincidencia esté pendiente.
"""

from django.db.models import Q

from ..models import ESTADOS_NO_VIGENTES, Animal, Caso, Coincidencia
from .completitud import faltantes_obligatorios


def _pendientes_vigentes(caso):
    return (
        Coincidencia.objects.filter(Q(caso_a=caso) | Q(caso_b=caso), estado=Coincidencia.Estado.PENDIENTE)
        .exclude(caso_a__estado__in=ESTADOS_NO_VIGENTES)
        .exclude(caso_b__estado__in=ESTADOS_NO_VIGENTES)
    )


def refrescar_marcas(caso, propagar=True):
    animales = list(Animal.objects.filter(caso_id=caso.pk))
    incompleto = bool(faltantes_obligatorios(caso, animales))
    duplicado = relacionado = False
    if caso.vigente:
        pendientes = _pendientes_vigentes(caso)
        duplicado = pendientes.filter(tipo=Coincidencia.Tipo.DUPLICADO).exists()
        relacionado = pendientes.filter(tipo=Coincidencia.Tipo.RELACIONADO).exists()
    Caso.objects.filter(pk=caso.pk).update(
        incompleto=incompleto, marca_duplicado=duplicado, marca_relacionado=relacionado
    )
    caso.incompleto, caso.marca_duplicado, caso.marca_relacionado = incompleto, duplicado, relacionado

    if propagar:
        # El estado de este caso puede cambiar las marcas de sus pares.
        pares = Coincidencia.objects.filter(Q(caso_a=caso) | Q(caso_b=caso)).select_related('caso_a', 'caso_b')
        for coincidencia in pares:
            refrescar_marcas(coincidencia.otro(caso), propagar=False)
