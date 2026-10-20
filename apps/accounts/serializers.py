import pyotp
from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer
from rest_framework_simplejwt.settings import api_settings

from .models import Organismo, Usuario


def verificar_totp(usuario, codigo):
    """Código de 6 dígitos de la app autenticadora (se acepta ±30 s por desfasaje de reloj)."""
    codigo = (codigo or '').replace(' ', '')
    if not (usuario.totp_secreto and codigo.isdigit() and len(codigo) == 6):
        return False
    return pyotp.TOTP(usuario.totp_secreto).verify(codigo, valid_window=1)


class OrganismoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organismo
        fields = ['id', 'nombre', 'tipo', 'activo']


class UsuarioSerializer(serializers.ModelSerializer):
    organismo_nombre = serializers.CharField(source='organismo.nombre', read_only=True, default=None)
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})

    class Meta:
        model = Usuario
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'telefono',
            'rol', 'organismo', 'organismo_nombre', 'is_active', 'last_login', 'totp_activo', 'password',
        ]
        read_only_fields = ['last_login', 'totp_activo']

    def validate_password(self, valor):
        validate_password(valor)
        return valor

    def validate(self, attrs):
        rol = attrs.get('rol', getattr(self.instance, 'rol', Usuario.Rol.AGENTE))
        organismo = attrs.get('organismo', getattr(self.instance, 'organismo', None))
        if rol in (Usuario.Rol.AGENTE, Usuario.Rol.ANALISTA) and organismo is None:
            raise serializers.ValidationError({'organismo': 'Los agentes y analistas deben pertenecer a un organismo.'})
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'La contraseña inicial es obligatoria.'})
        request = self.context.get('request')
        if self.instance is not None and request is not None and self.instance.pk == request.user.pk:
            if attrs.get('is_active') is False:
                raise serializers.ValidationError({'is_active': 'No podés desactivar tu propia cuenta.'})
            if 'rol' in attrs and attrs['rol'] != Usuario.Rol.ADMINISTRADOR:
                raise serializers.ValidationError({'rol': 'No podés quitarte el rol de administrador.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        usuario = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class UsuarioActualSerializer(serializers.ModelSerializer):
    """Lo que el front necesita para armar la cáscara según el rol."""

    organismo_nombre = serializers.CharField(source='organismo.nombre', read_only=True, default=None)
    nombre = serializers.CharField(source='nombre_completo', read_only=True)
    iniciales = serializers.SerializerMethodField()
    debe_configurar_2fa = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            'id', 'username', 'first_name', 'last_name', 'nombre', 'iniciales', 'email', 'rol', 'organismo',
            'organismo_nombre', 'totp_activo', 'debe_configurar_2fa',
        ]

    def get_iniciales(self, obj) -> str:
        partes = obj.nombre_completo.split()
        return ''.join(p[0] for p in partes[:2]).upper()

    def get_debe_configurar_2fa(self, obj) -> bool:
        # R.05 está «por corroborar» con los organismos: por defecto el doble factor es opcional.
        return bool(getattr(settings, 'SIRAM_2FA_OBLIGATORIO', False)) and not obj.totp_activo


class RestablecerPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_password(self, valor):
        validate_password(valor)
        return valor


class LoginSerializer(TokenObtainPairSerializer):
    """Usuario + contraseña y, si la cuenta tiene doble factor activo, el código de 6 dígitos (`codigo`).

    Sin código responde 401 con `codigo: "otp_requerido"` para que el front pida el segundo paso."""

    codigo = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        codigo = attrs.pop('codigo', '')
        TokenObtainSerializer.validate(self, attrs)  # credenciales (lanza 401 si son inválidas)
        usuario = self.user
        if usuario.totp_activo:
            if not codigo:
                raise AuthenticationFailed({'codigo': 'otp_requerido', 'detalle': 'Ingresá el código de tu app autenticadora.'})
            if not verificar_totp(usuario, codigo):
                raise AuthenticationFailed({'codigo': 'otp_invalido', 'detalle': 'El código es incorrecto o venció.'})
        refresh = self.get_token(usuario)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, usuario)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'usuario': UsuarioActualSerializer(usuario).data,
        }


class CodigoSerializer(serializers.Serializer):
    codigo = serializers.CharField()


class DesactivarDobleFactorSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    codigo = serializers.CharField()
