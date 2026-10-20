import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile

from .base import BaseAPITestCase

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF'


class PermisosPorRolTests(BaseAPITestCase):
    def setUp(self):
        self.numero = self.crear().json()['id']

    def test_sin_sesion_no_se_ve_nada(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/casos/').status_code, 401)

    def test_el_administrador_gestiona_accesos_pero_no_ve_casos(self):
        c = self.como(self.admin)
        self.assertEqual(c.get('/api/casos/').status_code, 403)
        self.assertEqual(c.get(f'/api/casos/{self.numero}/').status_code, 403)
        self.assertEqual(c.get('/api/usuarios/').status_code, 200)
        self.assertEqual(c.get('/api/consultas/estadisticas/').status_code, 200)

    def test_el_agente_no_administra_usuarios(self):
        self.assertEqual(self.como(self.agente).get('/api/usuarios/').status_code, 403)

    def test_el_analista_lee_pero_no_escribe_y_no_ve_datos_personales(self):
        c = self.como(self.analista)
        self.assertEqual(c.post('/api/casos/', self.cuerpo_caso(), format='json').status_code, 403)
        self.assertEqual(c.patch(f'/api/casos/{self.numero}/', {'lugarCiudad': 'X'}, format='json').status_code, 403)
        ficha = c.get(f'/api/casos/{self.numero}/').json()
        self.assertEqual(ficha['victima']['nombre'], 'M. S.')
        for campo in ('dni', 'telefono', 'email', 'direccion'):
            self.assertIsNone(ficha['victima'][campo], campo)
        self.assertEqual(ficha['lugarDireccion'], '')
        self.assertEqual(c.get('/api/casos/').json()['results'][0]['victima']['nombre'], 'M. S.')
        # No se puede averiguar quién es buscando por DNI.
        self.assertEqual(c.get('/api/casos/?q=58412336').json()['count'], 0)
        self.assertEqual(c.get('/api/coincidencias/').status_code, 200)

    def test_un_agente_puede_editar_casos_de_otro_organismo_por_defecto(self):
        r = self.como(self.agente_hospital).patch(f'/api/casos/{self.numero}/', {'lugarCiudad': 'Tolhuin'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_edicion_entre_organismos_puede_cerrarse(self):
        with self.settings(SIRAM_EDICION_ENTRE_ORGANISMOS=False):
            r = self.como(self.agente_hospital).patch(f'/api/casos/{self.numero}/', {'lugarCiudad': 'Tolhuin'}, format='json')
            self.assertEqual(r.status_code, 403)


class DocumentosTests(BaseAPITestCase):
    def test_subir_y_descargar_con_permisos(self):
        numero = self.crear().json()['id']
        c = self.como(self.agente)
        r = c.post(
            f'/api/casos/{numero}/documentos/',
            {'tipo': 'certificado_medico', 'archivo': SimpleUploadedFile('certificado.pdf', PDF, 'application/pdf')},
            format='multipart',
        )
        self.assertEqual(r.status_code, 201, r.content)
        doc_id = r.json()['id']
        self.assertEqual(r.json()['estadoValidacion'], 'pendiente')
        self.assertNotIn('archivo', r.json(), 'no se expone la ruta del archivo')
        descarga = c.get(f'/api/documentos/{doc_id}/descargar/')
        self.assertEqual(descarga.status_code, 200)
        self.assertEqual(b''.join(descarga.streaming_content), PDF)
        self.assertEqual(c.patch(f'/api/documentos/{doc_id}/', {'estadoValidacion': 'validado'}, format='json').status_code, 200)
        # Analista y administrador no acceden a los documentos.
        self.assertEqual(self.como(self.analista).get(f'/api/documentos/{doc_id}/descargar/').status_code, 403)
        self.assertEqual(self.como(self.admin).get(f'/api/documentos/{doc_id}/descargar/').status_code, 403)
        self.assertEqual(self.como(self.analista).get(f'/api/casos/{numero}/').json()['documentos'], [])

    def test_solo_acepta_pdf_o_imagenes_de_verdad(self):
        numero = self.crear().json()['id']
        r = self.como(self.agente).post(
            f'/api/casos/{numero}/documentos/',
            {'tipo': 'otro', 'archivo': SimpleUploadedFile('virus.pdf', b'MZ\x90\x00 no soy un pdf', 'application/pdf')},
            format='multipart',
        )
        self.assertEqual(r.status_code, 400)


class ConsultasTests(BaseAPITestCase):
    def setUp(self):
        self.crear()
        self.crear(
            victima={'nombre': 'Lucía', 'apellido': 'Ferreyra', 'dni': '27333444', 'edadDeclarada': 29},
            lugarCiudad='Río Grande', fechaHecho=self.fecha(40), lugarDireccion='Perito Moreno 320',
            animales=[{'especie': 'gato', 'tamano': 'chico', 'tenencia': 'propio', 'vacunado': 'si'}],
        )

    def test_estadisticas_cuentan_casos_vigentes(self):
        r = self.como(self.agente).get('/api/consultas/estadisticas/')
        self.assertEqual(r.status_code, 200, r.content)
        datos = r.json()
        self.assertEqual(datos['total'], 2)
        self.assertEqual({f['clave'] for f in datos['porCiudad']}, {'Ushuaia', 'Río Grande'})
        self.assertEqual({f['clave'] for f in datos['porEspecie']}, {'perro', 'gato'})
        franjas = {f['clave']: f['cantidad'] for f in datos['porFranjaEtaria']}
        self.assertEqual(franjas['5 a 14'], 1)
        self.assertEqual(franjas['25 a 44'], 1)
        self.assertEqual(len(datos['porMes']), 2)
        self.assertEqual(self.como(self.agente).get('/api/consultas/estadisticas/?ciudad=ushuaia').json()['total'], 1)

    def test_inicio(self):
        r = self.como(self.agente).get('/api/inicio/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['indicadores']['casosVigentes'], 2)

    def test_exportar_csv_no_incluye_datos_identificatorios(self):
        r = self.como(self.agente).get('/api/consultas/exportar/?formato=csv')
        self.assertEqual(r.status_code, 200, r.content)
        texto = r.content.decode('utf-8-sig')
        filas = list(csv.reader(io.StringIO(texto), delimiter=';'))
        self.assertEqual(len(filas), 3)
        self.assertNotIn('58412336', texto)
        self.assertNotIn('Sosa', texto)
        self.assertNotIn('2901-54-8820', texto)
        self.assertIn('M. S.', texto)

    def test_exportar_xlsx(self):
        r = self.como(self.analista).get('/api/consultas/exportar/?formato=xlsx')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.content.startswith(b'PK'))
        self.assertEqual(self.como(self.admin).get('/api/consultas/exportar/').status_code, 403)

    def test_ficha_pdf(self):
        numero = self.como(self.agente).get('/api/casos/').json()['results'][0]['id']
        r = self.como(self.agente).get(f'/api/casos/{numero}/ficha-pdf/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertEqual(self.como(self.analista).get(f'/api/casos/{numero}/ficha-pdf/').status_code, 403)

    def test_opciones_para_los_selects(self):
        r = self.como(self.agente).get('/api/opciones/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({e['valor'] for e in r.json()['estados']},
                         {'registrado', 'en_seguimiento', 'finalizado', 'desestimado', 'unificado'})
