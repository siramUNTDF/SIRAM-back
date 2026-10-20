"""Datos y ayudas comunes de los tests."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Organismo, Usuario
from apps.casos.models import EnteDenuncia, TipoEvento


class BaseAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zoonosis = Organismo.objects.create(nombre='Zoonosis Ushuaia', tipo='municipal')
        cls.hospital = Organismo.objects.create(nombre='Hospital Regional Ushuaia', tipo='salud')
        cls.clave = 'Clave-de-prueba-2026'
        cls.admin = Usuario.objects.create_user(
            'admin', 'admin@siram.test', cls.clave, rol=Usuario.Rol.ADMINISTRADOR, first_name='Ana', last_name='Admin'
        )
        cls.agente = Usuario.objects.create_user(
            'agente', 'agente@siram.test', cls.clave, rol=Usuario.Rol.AGENTE, organismo=cls.zoonosis,
            first_name='Daniela', last_name='Marchisoney',
        )
        cls.agente_hospital = Usuario.objects.create_user(
            'hospital', 'hospital@siram.test', cls.clave, rol=Usuario.Rol.AGENTE, organismo=cls.hospital,
            first_name='Hugo', last_name='Hospital',
        )
        cls.analista = Usuario.objects.create_user(
            'analista', 'analista@siram.test', cls.clave, rol=Usuario.Rol.ANALISTA, organismo=cls.zoonosis,
            first_name='Alba', last_name='Analista',
        )
        cls.tipo_evento = TipoEvento.objects.create(nombre='Ataque con mordedura')
        cls.ente = EnteDenuncia.objects.create(nombre='Zoonosis')

    # --- ayudas ---
    def como(self, usuario):
        self.client.force_authenticate(usuario)
        return self.client

    @staticmethod
    def fecha(dias_atras=2, hora=14):
        momento = timezone.localtime() - timedelta(days=dias_atras)
        return momento.replace(hour=hora, minute=20, second=0, microsecond=0).isoformat()

    def cuerpo_caso(self, **cambios):
        """Cuerpo de un alta, en camelCase como lo manda el front."""
        cuerpo = {
            'victima': {'nombre': 'Micaela', 'apellido': 'Sosa', 'dni': '58412336', 'edadDeclarada': 7,
                        'telefono': '2901-54-8820'},
            'tipoEvento': self.tipo_evento.pk,
            'fechaHecho': self.fecha(),
            'lugarDireccion': 'Kuanip 1240',
            'lugarCiudad': 'Ushuaia',
            'tipoLugar': 'via_publica',
            'situacionPersona': 'transito',
            'lesion': 'mordedura',
            'animales': [{'especie': 'perro', 'tamano': 'mediano', 'color': 'marrón y blanco', 'tenencia': 'ajeno'}],
        }
        cuerpo.update(cambios)
        return cuerpo

    def crear(self, usuario=None, esperado=201, **cambios):
        respuesta = self.como(usuario or self.agente).post('/api/casos/', self.cuerpo_caso(**cambios), format='json')
        self.assertEqual(respuesta.status_code, esperado, respuesta.content[:600])
        return respuesta
