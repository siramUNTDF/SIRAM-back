from django.urls import path
from rest_framework.routers import DefaultRouter

from .consultas import EstadisticasView, ExportarView, InicioView, OpcionesView
from .views import (
    AnimalViewSet,
    CasoViewSet,
    CoincidenciaViewSet,
    DenunciaViewSet,
    DocumentoViewSet,
    EnteDenunciaViewSet,
    TipoEventoViewSet,
)

router = DefaultRouter()
router.register('casos', CasoViewSet, basename='caso')
router.register('coincidencias', CoincidenciaViewSet, basename='coincidencia')
router.register('animales', AnimalViewSet, basename='animal')
router.register('denuncias', DenunciaViewSet, basename='denuncia')
router.register('documentos', DocumentoViewSet, basename='documento')
router.register('tipos-evento', TipoEventoViewSet, basename='tipo-evento')
router.register('entes', EnteDenunciaViewSet, basename='ente')

urlpatterns = [
    path('inicio/', InicioView.as_view(), name='inicio'),
    path('consultas/estadisticas/', EstadisticasView.as_view(), name='estadisticas'),
    path('consultas/exportar/', ExportarView.as_view(), name='exportar'),
    path('opciones/', OpcionesView.as_view(), name='opciones'),
] + router.urls
