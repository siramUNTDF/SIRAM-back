from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ActivarDobleFactorView,
    ConfigurarDobleFactorView,
    DesactivarDobleFactorView,
    LoginView,
    LogoutView,
    OrganismoViewSet,
    UsuarioViewSet,
    YoView,
)

router = DefaultRouter()
router.register('usuarios', UsuarioViewSet, basename='usuario')
router.register('organismos', OrganismoViewSet, basename='organismo')

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/yo/', YoView.as_view(), name='yo'),
    path('auth/2fa/configurar/', ConfigurarDobleFactorView.as_view(), name='2fa-configurar'),
    path('auth/2fa/activar/', ActivarDobleFactorView.as_view(), name='2fa-activar'),
    path('auth/2fa/desactivar/', DesactivarDobleFactorView.as_view(), name='2fa-desactivar'),
] + router.urls
