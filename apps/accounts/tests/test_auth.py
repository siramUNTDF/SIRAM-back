import pyotp
from rest_framework.test import APITestCase

from apps.accounts.models import Organismo, Usuario


class AutenticacionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organismo.objects.create(nombre='Zoonosis Ushuaia')
        cls.admin = Usuario.objects.create_user(
            'admin', 'admin@siram.test', 'Clave-de-prueba-2026', rol=Usuario.Rol.ADMINISTRADOR
        )
        cls.agente = Usuario.objects.create_user(
            'agente', 'agente@siram.test', 'Clave-de-prueba-2026', rol=Usuario.Rol.AGENTE, organismo=cls.org,
            first_name='Daniela', last_name='Marchisoney',
        )

    def login(self, usuario='agente', password='Clave-de-prueba-2026', **extra):
        return self.client.post('/api/auth/login/', {'username': usuario, 'password': password, **extra}, format='json')

    def test_login_devuelve_tokens_y_datos_para_la_cascara(self):
        r = self.login()
        self.assertEqual(r.status_code, 200, r.content)
        datos = r.json()
        self.assertTrue(datos['access'] and datos['refresh'])
        self.assertEqual(datos['usuario']['nombre'], 'Daniela Marchisoney')
        self.assertEqual(datos['usuario']['iniciales'], 'DM')
        self.assertEqual(datos['usuario']['rol'], 'agente')
        yo = self.client.get('/api/auth/yo/', HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        self.assertEqual(yo.status_code, 200)
        self.assertEqual(yo.json()['organismoNombre'], 'Zoonosis Ushuaia')

    def test_credenciales_invalidas(self):
        self.assertEqual(self.login(password='mala').status_code, 401)
        self.assertEqual(self.login(usuario='nadie').status_code, 401)

    def test_usuario_desactivado_no_entra(self):
        Usuario.objects.filter(pk=self.agente.pk).update(is_active=False)
        self.assertEqual(self.login().status_code, 401)

    def test_logout_invalida_el_refresh(self):
        refresh = self.login().json()['refresh']
        self.assertEqual(self.client.post('/api/auth/logout/', {'refresh': refresh}, format='json').status_code, 204)
        self.assertEqual(self.client.post('/api/auth/refresh/', {'refresh': refresh}, format='json').status_code, 401)

    def test_doble_factor(self):
        self.client.force_authenticate(self.agente)
        config = self.client.post('/api/auth/2fa/configurar/').json()
        totp = pyotp.TOTP(config['secreto'])
        self.assertTrue(config['otpauthUrl'].startswith('otpauth://totp/'))
        # Con un código incorrecto no se activa.
        self.assertEqual(self.client.post('/api/auth/2fa/activar/', {'codigo': '000000'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/2fa/activar/', {'codigo': totp.now()}, format='json').status_code, 200)

        self.client.force_authenticate(None)
        sin_codigo = self.login()
        self.assertEqual(sin_codigo.status_code, 401)
        self.assertEqual(sin_codigo.json()['codigo'], 'otp_requerido')
        self.assertEqual(self.login(codigo='123456').json()['codigo'], 'otp_invalido')
        ok = self.login(codigo=totp.now())
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertTrue(ok.json()['usuario']['totpActivo'])

    def test_el_administrador_restablece_el_doble_factor(self):
        Usuario.objects.filter(pk=self.agente.pk).update(totp_activo=True, totp_secreto=pyotp.random_base32())
        self.assertEqual(self.login().status_code, 401)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'/api/usuarios/{self.agente.pk}/restablecer-2fa/').status_code, 204)
        self.client.force_authenticate(None)
        self.assertEqual(self.login().status_code, 200)


class AdministracionDeUsuariosTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organismo.objects.create(nombre='Zoonosis Ushuaia')
        cls.admin = Usuario.objects.create_user(
            'admin', 'admin@siram.test', 'Clave-de-prueba-2026', rol=Usuario.Rol.ADMINISTRADOR
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_alta_con_organismo_y_rol(self):
        r = self.client.post(
            '/api/usuarios/',
            {'username': 'nuevo', 'email': 'nuevo@siram.test', 'firstName': 'Nora', 'lastName': 'Nueva',
             'rol': 'agente', 'organismo': self.org.pk, 'password': 'Otra-clave-segura-77'},
            format='json',
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn('password', r.json())
        self.assertTrue(Usuario.objects.get(username='nuevo').check_password('Otra-clave-segura-77'))

    def test_un_agente_necesita_organismo(self):
        r = self.client.post(
            '/api/usuarios/', {'username': 'x', 'email': 'x@x.test', 'rol': 'agente', 'password': 'Otra-clave-segura-77'},
            format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_contrasena_debil_rechazada(self):
        r = self.client.post(
            '/api/usuarios/',
            {'username': 'x', 'email': 'x@x.test', 'rol': 'administrador', 'password': '1234'},
            format='json',
        )
        self.assertEqual(r.status_code, 400)

    def test_baja_es_desactivar_y_no_se_puede_borrar(self):
        u = Usuario.objects.create_user('baja', 'baja@x.test', 'Clave-de-prueba-2026', rol='agente', organismo=self.org)
        self.assertEqual(self.client.delete(f'/api/usuarios/{u.pk}/').status_code, 405)
        r = self.client.patch(f'/api/usuarios/{u.pk}/', {'isActive': False}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.get(pk=u.pk).is_active)

    def test_el_administrador_no_puede_desactivarse_a_si_mismo(self):
        r = self.client.patch(f'/api/usuarios/{self.admin.pk}/', {'isActive': False}, format='json')
        self.assertEqual(r.status_code, 400)
