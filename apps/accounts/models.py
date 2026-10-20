from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Organismo(models.Model):
    """Ente que usa SIRAM (Zoonosis, Salud, CADIC...). Es un dato del caso, no una marca del sistema."""

    class Tipo(models.TextChoices):
        PROVINCIAL = 'provincial', 'Provincial'
        MUNICIPAL = 'municipal', 'Municipal'
        SALUD = 'salud', 'Salud'
        ACADEMICO = 'academico', 'Académico / científico'
        OTRO = 'otro', 'Otro'

    nombre = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OTRO)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name_plural = 'organismos'

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    """Cuenta de personal interno. Los ciudadanos no tienen cuenta (el canal público está en suspenso)."""

    class Rol(models.TextChoices):
        ADMINISTRADOR = 'administrador', 'Administrador del sistema'
        AGENTE = 'agente', 'Agente interno'
        ANALISTA = 'analista', 'Analista / Comité'

    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.AGENTE)
    organismo = models.ForeignKey(
        Organismo, null=True, blank=True, on_delete=models.PROTECT, related_name='usuarios'
    )
    telefono = models.CharField(max_length=30, blank=True)
    # Doble factor (R.05, TOTP: Google Authenticator, Authy, etc.). El secreto solo se confirma al activar.
    totp_secreto = models.CharField(max_length=64, blank=True, editable=False)
    totp_activo = models.BooleanField(default=False, editable=False)

    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['username']

    def clean(self):
        super().clean()
        if self.rol in (self.Rol.AGENTE, self.Rol.ANALISTA) and not self.organismo_id:
            raise ValidationError({'organismo': 'Los agentes y analistas deben pertenecer a un organismo.'})

    @property
    def nombre_completo(self):
        return self.get_full_name() or self.username

    @property
    def es_administrador(self):
        return self.rol == self.Rol.ADMINISTRADOR

    @property
    def es_agente(self):
        return self.rol == self.Rol.AGENTE

    @property
    def es_analista(self):
        return self.rol == self.Rol.ANALISTA

    def __str__(self):
        return self.nombre_completo
