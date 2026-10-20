"""R.29: historial de modificaciones. Quién, cuándo y qué cambió.

Los datos personales (DNI, teléfono...) NO se copian a la auditoría: solo queda constancia de que cambiaron.
"""

from ..models import EventoAuditoria

CAMPOS_CASO = [
    'tipo_evento', 'fecha_hecho', 'lugar_direccion', 'lugar_ciudad', 'latitud', 'longitud', 'tipo_lugar',
    'situacion_persona', 'lesion', 'lesion_localizacion', 'lesion_gravedad', 'atencion_medica',
    'hizo_denuncia', 'motivo_no_denuncia', 'observaciones',
]
CAMPOS_PERSONA = [
    'nombre', 'apellido', 'dni', 'fecha_nacimiento', 'edad_declarada', 'sexo', 'telefono', 'email',
    'direccion', 'ciudad',
]
SENSIBLES = {
    'nombre', 'apellido', 'dni', 'fecha_nacimiento', 'telefono', 'email', 'direccion',
    'tenedor_nombre', 'tenedor_telefono', 'tenedor_direccion', 'observaciones',
}


def registrar(caso, usuario, accion, detalle=None):
    return EventoAuditoria.objects.create(caso=caso, usuario=usuario, accion=accion, detalle=detalle or {})


def _texto(valor):
    return None if valor is None else str(valor)


def instantanea(caso):
    """Valores actuales de los campos editables del caso y de su víctima, como texto."""
    datos = {campo: _texto(getattr(caso, campo)) for campo in CAMPOS_CASO}
    for campo in CAMPOS_PERSONA:
        datos[f'victima.{campo}'] = _texto(getattr(caso.victima, campo))
    return datos


def diferencias(antes, despues):
    cambios = {}
    for clave, valor_antes in antes.items():
        valor_despues = despues.get(clave)
        if valor_antes == valor_despues:
            continue
        if clave.split('.')[-1] in SENSIBLES:
            cambios[clave] = {'sensible': True}
        else:
            cambios[clave] = {'antes': valor_antes, 'despues': valor_despues}
    return cambios


def instantanea_enmascarada(caso):
    """Foto del caso para dejar en la auditoría (p. ej. al consolidar), sin datos personales."""
    datos = instantanea(caso)
    return {k: ('***' if v and k.split('.')[-1] in SENSIBLES else v) for k, v in datos.items()}
