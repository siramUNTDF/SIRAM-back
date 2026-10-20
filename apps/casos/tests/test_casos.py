from django.utils import timezone

from apps.casos.models import Caso, EventoAuditoria

from .base import BaseAPITestCase


class AltaDeCasosTests(BaseAPITestCase):
    def test_alta_devuelve_la_ficha_con_numero_y_marcas(self):
        r = self.crear()
        datos = r.json()
        self.assertEqual(datos['id'], f'C-{timezone.localdate().year}-0001')
        self.assertEqual(datos['estado'], 'registrado')
        self.assertEqual(datos['origen'], 'Zoonosis Ushuaia')
        self.assertEqual(datos['marcas'], [])
        self.assertEqual(datos['victima']['dni'], '58412336')
        self.assertEqual(len(datos['animales']), 1)
        self.assertGreater(datos['completitud']['completos'], 5)

    def test_el_dni_es_obligatorio(self):
        r = self.crear(esperado=400, victima={'nombre': 'Sin', 'apellido': 'Dni'})
        self.assertIn('dni', r.json()['victima'])

    def test_dni_con_puntos_se_normaliza_y_uno_invalido_se_rechaza(self):
        r = self.crear(victima={'nombre': 'A', 'apellido': 'B', 'dni': '12.345.678'})
        self.assertEqual(r.json()['victima']['dni'], '12345678')
        self.crear(esperado=400, victima={'nombre': 'A', 'apellido': 'B', 'dni': '12'})

    def test_fecha_futura_se_rechaza(self):
        self.crear(esperado=400, fechaHecho=self.fecha(dias_atras=-3))

    def test_faltan_datos_obligatorios_marca_incompleto(self):
        r = self.crear(fechaHecho=None, lugarDireccion='')
        self.assertEqual(r.json()['marcas'], ['incompleto'])
        self.assertIn('Fecha del hecho', r.json()['completitud']['faltantesObligatorios'])

    def test_los_numeros_son_correlativos(self):
        a = self.crear(victima={'nombre': 'A', 'apellido': 'A', 'dni': '10000001'}, fechaHecho=self.fecha(30)).json()
        b = self.crear(victima={'nombre': 'B', 'apellido': 'B', 'dni': '10000002'}, fechaHecho=self.fecha(60)).json()
        self.assertTrue(a['id'].endswith('0001'))
        self.assertTrue(b['id'].endswith('0002'))

    def test_el_alta_deja_auditoria(self):
        numero = self.crear().json()['id']
        evento = EventoAuditoria.objects.get(caso__numero=numero)
        self.assertEqual(evento.accion, 'creado')
        self.assertEqual(evento.usuario, self.agente)

    def test_alta_con_denuncia_anotada(self):
        r = self.crear(
            hizoDenuncia='si',
            denuncias=[{'ente': self.ente.pk, 'numero': '123/26', 'fecha': '2026-09-13',
                        'realizadaPor': {'nombre': 'Carla', 'apellido': 'Sosa', 'dni': '32114887'},
                        'vinculo': 'Madre'}],
        )
        denuncia = r.json()['denuncias'][0]
        self.assertEqual(denuncia['enteNombre'], 'Zoonosis')
        self.assertEqual(denuncia['realizadaPor']['apellido'], 'Sosa')


class ListaYFichaTests(BaseAPITestCase):
    def test_la_lista_tiene_la_forma_de_los_datos_de_ejemplo_del_front(self):
        self.crear()
        r = self.como(self.agente).get('/api/casos/')
        self.assertEqual(r.status_code, 200)
        fila = r.json()['results'][0]
        self.assertEqual(
            set(fila), {'id', 'fechaHecho', 'victima', 'lugar', 'animal', 'lesion', 'estado', 'motivoEspera',
                        'unificadoEn', 'origen', 'marcas'},
        )
        self.assertEqual(fila['victima']['nombre'], 'Micaela Sosa')
        self.assertEqual(fila['victima']['edad'], 7)
        self.assertEqual(fila['lugar'], {'direccion': 'Kuanip 1240', 'ciudad': 'Ushuaia'})
        self.assertEqual(fila['animal'], {'especie': 'Perro', 'tamano': 'Mediano'})
        self.assertEqual(fila['lesion'], 'Mordedura')
        # El front separa la fecha a mano en 'T': tiene que haber una.
        self.assertIn('T', fila['fechaHecho'])

    def test_busqueda_de_texto_y_filtros(self):
        self.crear()
        self.crear(
            victima={'nombre': 'Ramiro', 'apellido': 'Beltrán', 'dni': '20111222'},
            lugarCiudad='Río Grande', fechaHecho=self.fecha(40), lugarDireccion='Alem 2190',
        )
        c = self.como(self.agente)
        self.assertEqual(c.get('/api/casos/?q=sosa').json()['count'], 1)
        self.assertEqual(c.get('/api/casos/?q=20111222').json()['count'], 1)
        self.assertEqual(c.get('/api/casos/?ciudad=grande').json()['count'], 1)
        self.assertEqual(c.get('/api/casos/?especie=gato').json()['count'], 0)
        self.assertEqual(c.get('/api/casos/?especie=perro').json()['count'], 2)

    def test_ficha_por_numero(self):
        numero = self.crear().json()['id']
        r = self.como(self.agente).get(f'/api/casos/{numero}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['id'], numero)
        self.assertEqual(self.como(self.agente).get('/api/casos/C-2026-9999/').status_code, 404)

    def test_contadores_respetan_marcas_y_vigencia(self):
        self.crear(fechaHecho=None)  # incompleto
        c = self.como(self.agente)
        cont = c.get('/api/casos/contadores/').json()
        self.assertEqual(cont['incompleto'], 1)
        self.assertEqual(cont['todos'], 1)
        numero = c.get('/api/casos/').json()['results'][0]['id']
        c.post(f'/api/casos/{numero}/desestimar/', {'motivo': 'Carga duplicada por error'}, format='json')
        cont = c.get('/api/casos/contadores/').json()
        self.assertEqual(cont['incompleto'], 0, 'un caso desestimado no cuenta en las listas de trabajo')
        self.assertEqual(cont['todos'], 1, '«Todos» sí muestra todos los casos')
        self.assertEqual(c.get('/api/casos/?marca=incompleto').json()['count'], 0)

    def test_modificar_un_caso_deja_constancia_sin_copiar_datos_personales(self):
        numero = self.crear().json()['id']
        r = self.como(self.agente).patch(
            f'/api/casos/{numero}/', {'lugarCiudad': 'Tolhuin', 'victima': {'telefono': '2901-55-1234'}}, format='json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        evento = EventoAuditoria.objects.filter(caso__numero=numero, accion='editado').get()
        cambios = evento.detalle['cambios']
        self.assertEqual(cambios['lugar_ciudad'], {'antes': 'Ushuaia', 'despues': 'Tolhuin'})
        self.assertEqual(cambios['victima.telefono'], {'sensible': True})
        self.assertNotIn('2901', str(cambios))

    def test_la_auditoria_no_se_puede_modificar_ni_borrar(self):
        numero = self.crear().json()['id']
        evento = EventoAuditoria.objects.filter(caso__numero=numero).first()
        evento.accion = 'editado'
        with self.assertRaises(PermissionError):
            evento.save()
        with self.assertRaises(PermissionError):
            evento.delete()

    def test_endpoint_de_auditoria(self):
        numero = self.crear().json()['id']
        r = self.como(self.agente).get(f'/api/casos/{numero}/auditoria/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]['usuario'], 'Daniela Marchisoney')
        self.assertEqual(self.como(self.analista).get(f'/api/casos/{numero}/auditoria/').status_code, 403)


class EstadosTests(BaseAPITestCase):
    def setUp(self):
        self.numero = self.crear().json()['id']

    def cambiar(self, **datos):
        return self.como(self.agente).post(f'/api/casos/{self.numero}/cambiar-estado/', datos, format='json')

    def test_en_seguimiento_exige_motivo_de_espera(self):
        self.assertEqual(self.cambiar(estado='en_seguimiento').status_code, 400)
        r = self.cambiar(estado='en_seguimiento', motivoEspera='contacto')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['estado'], 'en_seguimiento')
        self.assertEqual(r.json()['motivoEspera'], 'contacto')

    def test_desestimar_exige_motivo_y_no_borra(self):
        self.assertEqual(self.cambiar(estado='desestimado').status_code, 400)
        r = self.como(self.agente).post(f'/api/casos/{self.numero}/desestimar/', {'motivo': 'No corresponde'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['estado'], 'desestimado')
        self.assertTrue(Caso.objects.filter(numero=self.numero).exists())

    def test_no_se_puede_pasar_a_unificado_a_mano(self):
        self.assertEqual(self.cambiar(estado='unificado').status_code, 400)

    def test_finalizar_y_volver_a_seguimiento(self):
        self.assertEqual(self.cambiar(estado='finalizado').json()['estado'], 'finalizado')
        r = self.cambiar(estado='en_seguimiento', motivoEspera='certificado')
        self.assertEqual(r.json()['motivoEspera'], 'certificado')


class DuplicadosTests(BaseAPITestCase):
    def test_mismo_dni_y_fecha_avisa_antes_de_crear(self):
        self.crear()
        r = self.crear(usuario=self.agente_hospital, esperado=409)
        datos = r.json()
        self.assertEqual(datos['codigo'], 'posible_duplicado')
        candidato = datos['candidatos'][0]
        self.assertEqual(candidato['tipo'], 'duplicado')
        self.assertEqual(candidato['fuerza'], 'fuerte')
        senales = {s['clave']: s['resultado'] for s in candidato['senales']}
        self.assertEqual(senales['dni'], 'coincide')
        self.assertEqual(Caso.objects.count(), 1, 'el alta rechazada no deja nada guardado')

    def test_rechazar_el_alta_no_gasta_numeros(self):
        self.crear()
        self.crear(usuario=self.agente_hospital, esperado=409)
        b = self.crear(victima={'nombre': 'Otro', 'apellido': 'Caso', 'dni': '30999888'}, fechaHecho=self.fecha(50))
        self.assertTrue(b.json()['id'].endswith('0002'))

    def test_confirmando_se_crea_y_ambos_quedan_marcados(self):
        a = self.crear().json()['id']
        b = self.crear(usuario=self.agente_hospital, confirmarDuplicado=True).json()['id']
        lista = {f['id']: f for f in self.como(self.agente).get('/api/casos/').json()['results']}
        self.assertIn('duplicado', lista[a]['marcas'])
        self.assertIn('duplicado', lista[b]['marcas'])
        self.assertEqual(self.como(self.agente).get('/api/casos/contadores/').json()['duplicado'], 2)
        self.assertEqual(self.como(self.agente).get('/api/coincidencias/?tipo=duplicado').json()['count'], 1)

    def test_el_mismo_dni_meses_despues_no_es_el_mismo_incidente(self):
        self.crear()
        self.crear(fechaHecho=self.fecha(dias_atras=120))  # otra mordedura de la misma persona
        self.assertEqual(self.como(self.agente).get('/api/coincidencias/').json()['count'], 0)

    def test_consolidar_es_irreversible_y_conserva_el_dato_que_falta(self):
        self.crear()
        self.crear(
            usuario=self.agente_hospital, confirmarDuplicado=True,
            victima={'nombre': 'Micaela', 'apellido': 'Sosa', 'dni': '58412336', 'email': 'madre@correo.test'},
            lugarDireccion='Kuanip 1240', lesion='mordedura', lesionGravedad='leve',
        )
        c = self.como(self.agente)
        pendiente = c.get('/api/coincidencias/?tipo=duplicado').json()['results'][0]
        # Sin confirmación explícita no se consolida.
        self.assertEqual(c.post(f"/api/coincidencias/{pendiente['id']}/consolidar/", {}, format='json').status_code, 400)

        r = c.post(f"/api/coincidencias/{pendiente['id']}/consolidar/", {'confirmacion': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        casos = {f['id']: f for f in c.get('/api/casos/').json()['results']}
        unificados = [f for f in casos.values() if f['estado'] == 'unificado']
        self.assertEqual(len(unificados), 1)
        absorbido = unificados[0]
        principal = casos[absorbido['unificadoEn']]
        self.assertEqual(principal['marcas'], [])
        self.assertEqual(absorbido['marcas'], [], 'un caso unificado no conserva la marca de duplicado')
        ficha = c.get(f"/api/casos/{principal['id']}/").json()
        self.assertEqual(ficha['victima']['email'], 'madre@correo.test', 'se conserva el dato que solo tenía uno')
        self.assertEqual(ficha['lesionGravedad'], 'leve')
        # El caso absorbido sigue existiendo, con su historia.
        self.assertTrue(Caso.objects.filter(numero=absorbido['id']).exists())
        # No se puede deshacer ni repetir.
        again = c.post(f"/api/coincidencias/{pendiente['id']}/consolidar/", {'confirmacion': True}, format='json')
        self.assertEqual(again.status_code, 400)
        # Un caso unificado no se edita.
        self.assertEqual(c.patch(f"/api/casos/{absorbido['id']}/", {'lugarCiudad': 'X'}, format='json').status_code, 400)

    def test_elegir_campo_por_campo(self):
        self.crear(lugarDireccion='Kuanip 1240')
        self.crear(usuario=self.agente_hospital, confirmarDuplicado=True, lugarDireccion='Kuanip 1250')
        c = self.como(self.agente)
        pendiente = c.get('/api/coincidencias/?tipo=duplicado').json()['results'][0]
        detalle = c.get(f"/api/coincidencias/{pendiente['id']}/").json()
        principal = detalle['casoA']['id']
        c.post(
            f"/api/coincidencias/{pendiente['id']}/consolidar/",
            {'superviviente': principal, 'campos': {'lugar_direccion': 'absorbido'}, 'confirmacion': True},
            format='json',
        )
        self.assertEqual(c.get(f'/api/casos/{principal}/').json()['lugarDireccion'], 'Kuanip 1250')

    def test_descartar_quita_la_marca(self):
        self.crear()
        self.crear(usuario=self.agente_hospital, confirmarDuplicado=True)
        c = self.como(self.agente)
        pendiente = c.get('/api/coincidencias/').json()['results'][0]
        r = c.post(f"/api/coincidencias/{pendiente['id']}/descartar/", {'nota': 'Son hermanos'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(c.get('/api/casos/contadores/').json()['duplicado'], 0)


class EventosRelacionadosTests(BaseAPITestCase):
    def crear_par(self):
        a = self.crear(
            victima={'nombre': 'Ramiro', 'apellido': 'Beltrán', 'dni': '30111222'},
            lugarDireccion='Gobernador Paz 845', animales=[{'especie': 'perro', 'tamano': 'grande', 'tenencia': 'ajeno'}],
        ).json()['id']
        b = self.crear(
            usuario=self.agente_hospital,
            victima={'nombre': 'Nicolás', 'apellido': 'Vera', 'dni': '31222333'},
            lugarDireccion='Gobernador Paz 845', animales=[{'especie': 'perro', 'tamano': 'grande', 'tenencia': 'ajeno'}],
        ).json()['id']
        return a, b

    def test_dos_victimas_del_mismo_animal_son_un_evento_relacionado_no_un_duplicado(self):
        a, b = self.crear_par()
        lista = {f['id']: f for f in self.como(self.agente).get('/api/casos/').json()['results']}
        self.assertEqual(lista[a]['marcas'], ['relacionado'])
        self.assertEqual(lista[b]['marcas'], ['relacionado'])
        self.assertEqual(self.como(self.agente).get('/api/casos/contadores/').json()['duplicado'], 0)

    def test_nunca_se_consolida_un_evento_relacionado(self):
        self.crear_par()
        c = self.como(self.agente)
        item = c.get('/api/coincidencias/?tipo=relacionado').json()['results'][0]
        r = c.post(f"/api/coincidencias/{item['id']}/consolidar/", {'confirmacion': True}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Caso.objects.filter(estado='unificado').count(), 0)

    def test_vincular_es_reversible(self):
        self.crear_par()
        c = self.como(self.agente)
        item = c.get('/api/coincidencias/?tipo=relacionado').json()['results'][0]
        self.assertEqual(c.post(f"/api/coincidencias/{item['id']}/vincular/").status_code, 200)
        self.assertEqual(c.get('/api/casos/contadores/').json()['relacionado'], 0)
        self.assertEqual(Caso.objects.exclude(estado='registrado').count(), 0, 'los dos casos siguen vivos')
        self.assertEqual(c.post(f"/api/coincidencias/{item['id']}/desvincular/").status_code, 200)
        self.assertEqual(c.get('/api/casos/contadores/').json()['relacionado'], 2)
