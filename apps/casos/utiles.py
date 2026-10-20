import math
import re
import unicodedata


def normalizar(texto):
    """Minúsculas, sin tildes y con espacios simples: para comparar nombres y direcciones."""
    texto = unicodedata.normalize('NFD', str(texto or ''))
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', texto).strip().lower()


def solo_digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def telefono_clave(texto):
    """Clave para comparar teléfonos: los últimos 8 dígitos (ignora prefijos 0, 15, +54...)."""
    digitos = solo_digitos(texto)
    return digitos[-8:] if len(digitos) >= 7 else ''


def distancia_metros(lat1, lon1, lat2, lon2):
    """Distancia aproximada (haversine) entre dos coordenadas."""
    radio = 6371000
    f1, f2 = math.radians(float(lat1)), math.radians(float(lat2))
    df = f2 - f1
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(a))


def iniciales(texto):
    """'Micaela Sosa' -> 'M. S.' (para quien no debe ver el nombre completo)."""
    partes = str(texto or '').split()
    return ' '.join(p[0].upper() + '.' for p in partes) if partes else ''
