from django.contrib import admin

from .models import Animal, Caso, Coincidencia, Denuncia, Documento, EnteDenuncia, EventoAuditoria, Persona, Seguimiento, TipoEvento


class SoloLectura(admin.ModelAdmin):
    """Los casos se gestionan desde la API y el front; el admin de Django es solo para consulta."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Caso)
class CasoAdmin(SoloLectura):
    list_display = ('numero', 'estado', 'organismo', 'fecha_hecho', 'incompleto')
    list_filter = ('estado', 'organismo')
    search_fields = ('numero',)


@admin.register(EventoAuditoria)
class AuditoriaAdmin(SoloLectura):
    list_display = ('creado_en', 'caso', 'usuario', 'accion')
    list_filter = ('accion',)


admin.site.register(TipoEvento)
admin.site.register(EnteDenuncia)
