from django.db import transaction
from django.utils import timezone

from ..models import SecuenciaCaso


def siguiente_numero():
    """Devuelve (anio, secuencia, 'C-2026-0418'). Usar dentro de la transacción que crea el caso:
    el bloqueo de fila evita que dos altas simultáneas tomen el mismo número."""
    anio = timezone.localdate().year
    with transaction.atomic():
        contador, _ = SecuenciaCaso.objects.select_for_update().get_or_create(anio=anio, defaults={'ultimo': 0})
        contador.ultimo += 1
        contador.save(update_fields=['ultimo'])
    return anio, contador.ultimo, f'C-{anio}-{contador.ultimo:04d}'
