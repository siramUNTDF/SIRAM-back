import pyotp
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Organismo, Usuario
from .permisos import EsAdministrador, LecturaPersonalEscrituraAdmin
from .serializers import (
    CodigoSerializer,
    DesactivarDobleFactorSerializer,
    LoginSerializer,
    OrganismoSerializer,
    RestablecerPasswordSerializer,
    UsuarioActualSerializer,
    UsuarioSerializer,
    verificar_totp,
)


class LoginView(TokenObtainPairView):
    """R.02: autenticación. Devuelve access, refresh y los datos del usuario."""

    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class LogoutView(APIView):
    """Invalida el refresh token (la sesión deja de poder renovarse).

    Es público a propósito: el propio refresh token es la credencial, así se puede cerrar sesión
    aunque el access token ya haya vencido."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('refresh')
        if not token:
            return Response({'detalle': 'Falta el token de renovación.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            pass  # ya vencido o invalidado: el resultado buscado es el mismo
        return Response(status=status.HTTP_204_NO_CONTENT)


class YoView(APIView):
    def get(self, request):
        return Response(UsuarioActualSerializer(request.user).data)


class ConfigurarDobleFactorView(APIView):
    """Paso 1 del doble factor: genera el secreto y la URL `otpauth://` (el front la muestra como QR)."""

    def post(self, request):
        usuario = request.user
        if usuario.totp_activo:
            return Response({'detalle': 'El doble factor ya está activo.'}, status=status.HTTP_400_BAD_REQUEST)
        usuario.totp_secreto = pyotp.random_base32()
        usuario.save(update_fields=['totp_secreto'])
        url = pyotp.TOTP(usuario.totp_secreto).provisioning_uri(
            name=usuario.email or usuario.username, issuer_name='SIRAM'
        )
        return Response({'secreto': usuario.totp_secreto, 'otpauth_url': url})


class ActivarDobleFactorView(APIView):
    """Paso 2: confirma con un código de la app que quedó bien configurado."""

    def post(self, request):
        serializer = CodigoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = request.user
        if not verificar_totp(usuario, serializer.validated_data['codigo']):
            return Response({'detalle': 'El código es incorrecto o venció.'}, status=status.HTTP_400_BAD_REQUEST)
        usuario.totp_activo = True
        usuario.save(update_fields=['totp_activo'])
        return Response(UsuarioActualSerializer(usuario).data)


class DesactivarDobleFactorView(APIView):
    def post(self, request):
        serializer = DesactivarDobleFactorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = request.user
        d = serializer.validated_data
        if not (usuario.check_password(d['password']) and verificar_totp(usuario, d['codigo'])):
            return Response({'detalle': 'Contraseña o código incorrectos.'}, status=status.HTTP_400_BAD_REQUEST)
        usuario.totp_secreto, usuario.totp_activo = '', False
        usuario.save(update_fields=['totp_secreto', 'totp_activo'])
        return Response(UsuarioActualSerializer(usuario).data)


class UsuarioViewSet(viewsets.ModelViewSet):
    """R.01: ABM de cuentas. Sin DELETE: la baja es desactivar (`isActive: false`)."""

    queryset = Usuario.objects.select_related('organismo').order_by('username')
    serializer_class = UsuarioSerializer
    permission_classes = [EsAdministrador]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['rol', 'organismo', 'is_active']

    @action(detail=True, methods=['post'], url_path='restablecer-password')
    def restablecer_password(self, request, pk=None):
        usuario = self.get_object()
        serializer = RestablecerPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario.set_password(serializer.validated_data['password'])
        usuario.save(update_fields=['password'])
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=True, methods=['post'], url_path='restablecer-2fa')
    def restablecer_2fa(self, request, pk=None):
        """Para quien perdió el celular: el usuario vuelve a configurar el doble factor desde cero."""
        usuario = self.get_object()
        usuario.totp_secreto, usuario.totp_activo = '', False
        usuario.save(update_fields=['totp_secreto', 'totp_activo'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganismoViewSet(viewsets.ModelViewSet):
    queryset = Organismo.objects.all()
    serializer_class = OrganismoSerializer
    permission_classes = [LecturaPersonalEscrituraAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    pagination_class = None
    filterset_fields = ['activo', 'tipo']
