"""Permisos por rol (R.03, R.16, R.21). Se aplican en el servidor: no dependen de lo que muestre la interfaz."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario

Rol = Usuario.Rol


def con_roles(*roles):
    """Fábrica de permisos: deja pasar solo a usuarios activos con alguno de los roles."""

    class ConRoles(BasePermission):
        message = 'Tu rol no tiene permiso para esta operación.'

        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and u.is_active and u.rol in roles)

    ConRoles.__name__ = 'ConRoles_' + '_'.join(roles)
    return ConRoles


EsAdministrador = con_roles(Rol.ADMINISTRADOR)
EsAgente = con_roles(Rol.AGENTE)
EsAgenteOAnalista = con_roles(Rol.AGENTE, Rol.ANALISTA)
EsPersonalSiram = con_roles(Rol.ADMINISTRADOR, Rol.AGENTE, Rol.ANALISTA)


class LecturaPersonalEscrituraAdmin(BasePermission):
    """Catálogos y organismos: los lee cualquier usuario interno, los modifica el administrador."""

    message = 'Solo el administrador puede modificar este recurso.'

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.is_active):
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.rol == Rol.ADMINISTRADOR


class LecturaCasos(BasePermission):
    """Casos: leen agentes y analistas; escriben solo agentes. El administrador no ve datos de casos
    (su función es exclusivamente la administración de accesos)."""

    message = 'Tu rol no tiene permiso para esta operación sobre casos.'

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.is_active):
            return False
        if request.method in SAFE_METHODS:
            return u.rol in (Rol.AGENTE, Rol.ANALISTA)
        return u.rol == Rol.AGENTE


def debe_ocultar_datos_personales(usuario):
    """El analista/comité trabaja con datos epidemiológicos, no con datos identificatorios."""
    return usuario.is_authenticated and usuario.rol == Rol.ANALISTA
