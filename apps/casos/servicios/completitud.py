"""R.08: casos incompletos. Define qué datos son obligatorios y cuánto tiene cargado un caso."""

from ..models import Animal, Caso


def _tiene(valor):
    return bool((valor or '').strip()) if isinstance(valor, str) else valor is not None


def _conocido(valor):
    return bool(valor) and valor != 'sin_dato'


# (clave, etiqueta, función(caso, animales, n_denuncias) -> bool)
OBLIGATORIOS = [
    ('fecha_hecho', 'Fecha del hecho', lambda c, a, d: c.fecha_hecho is not None),
    ('lugar_ciudad', 'Ciudad', lambda c, a, d: _tiene(c.lugar_ciudad)),
    ('lugar_direccion', 'Lugar del hecho', lambda c, a, d: _tiene(c.lugar_direccion)),
    ('situacion_persona', 'Situación de la persona', lambda c, a, d: _conocido(c.situacion_persona)),
    ('animal_tenencia', 'Animal propio o ajeno', lambda c, a, d: any(_conocido(x.tenencia) for x in a)),
]

# Datos que suman a la completitud ("38 de 50 campos") sin bloquear el caso.
DESEABLES = [
    ('victima_nombre', 'Nombre de la víctima', lambda c, a, d: _tiene(c.victima.nombre)),
    ('victima_apellido', 'Apellido de la víctima', lambda c, a, d: _tiene(c.victima.apellido)),
    ('victima_dni', 'DNI de la víctima', lambda c, a, d: _tiene(c.victima.dni)),
    ('victima_edad', 'Edad de la víctima', lambda c, a, d: c.victima.edad_al(c.fecha_hecho) is not None),
    ('victima_sexo', 'Sexo de la víctima', lambda c, a, d: _conocido(c.victima.sexo)),
    ('victima_telefono', 'Teléfono de contacto', lambda c, a, d: _tiene(c.victima.telefono)),
    ('victima_direccion', 'Domicilio de la víctima', lambda c, a, d: _tiene(c.victima.direccion)),
    ('tipo_evento', 'Tipo de evento', lambda c, a, d: c.tipo_evento_id is not None),
    ('tipo_lugar', 'Tipo de lugar', lambda c, a, d: _conocido(c.tipo_lugar)),
    ('coordenadas', 'Ubicación en el mapa', lambda c, a, d: c.latitud is not None and c.longitud is not None),
    ('lesion', 'Tipo de lesión', lambda c, a, d: _conocido(c.lesion)),
    ('lesion_localizacion', 'Zona del cuerpo', lambda c, a, d: _tiene(c.lesion_localizacion)),
    ('lesion_gravedad', 'Gravedad', lambda c, a, d: _conocido(c.lesion_gravedad)),
    ('atencion_medica', 'Atención médica', lambda c, a, d: _conocido(c.atencion_medica)),
    ('hizo_denuncia', '¿Hizo denuncia?', lambda c, a, d: _conocido(c.hizo_denuncia)),
    ('animal_especie', 'Especie del animal', lambda c, a, d: bool(a)),
    ('animal_tamano', 'Tamaño del animal', lambda c, a, d: any(_conocido(x.tamano) for x in a)),
    ('animal_vacunado', 'Vacunación del animal', lambda c, a, d: any(_conocido(x.vacunado) for x in a)),
    ('animal_identificacion', 'Chip / identificación del animal', lambda c, a, d: any(_tiene(x.identificacion) for x in a)),
    ('animal_antecedentes', 'Antecedentes de ataques del animal', lambda c, a, d: any(_conocido(x.antecedentes_ataques) for x in a)),
]


def _contexto(caso, animales, n_denuncias):
    if animales is None:
        animales = list(Animal.objects.filter(caso_id=caso.pk))
    if n_denuncias is None:
        n_denuncias = caso.denuncias.count()
    return animales, n_denuncias


def faltantes_obligatorios(caso, animales=None, n_denuncias=None):
    animales, n_denuncias = _contexto(caso, animales, n_denuncias)
    return [etiqueta for _, etiqueta, ok in OBLIGATORIOS if not ok(caso, animales, n_denuncias)]


def completitud(caso, animales=None, n_denuncias=None):
    animales, n_denuncias = _contexto(caso, animales, n_denuncias)
    todos = OBLIGATORIOS + DESEABLES
    completos = sum(1 for _, _, ok in todos if ok(caso, animales, n_denuncias))
    return {
        'completos': completos,
        'total': len(todos),
        'faltantes_obligatorios': [e for _, e, ok in OBLIGATORIOS if not ok(caso, animales, n_denuncias)],
    }
