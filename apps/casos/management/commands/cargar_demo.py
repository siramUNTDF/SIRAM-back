"""Carga catálogos y datos de ejemplo para desarrollo (equivalentes a src/mocks/casos.js del front).

Uso:  python manage.py cargar_demo [--clave CLAVE] [--solo-catalogos]

Es idempotente para organismos, usuarios y catálogos. Los casos solo se cargan si todavía no hay ninguno.
NO usar en producción: crea usuarios con una clave conocida.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Organismo, Usuario
from apps.casos.models import Caso, EnteDenuncia, Estado, MotivoEspera, TipoEvento
from apps.casos.servicios import casos as servicios

ORGANISMOS = [
    ('Zoonosis Ushuaia', 'municipal'),
    ('Hospital Regional Ushuaia', 'salud'),
    ('Hospital Regional RG', 'salud'),
    ('CAPS 3', 'salud'),
    ('CAPS 4', 'salud'),
    ('CAPS 5', 'salud'),
    ('CADIC', 'academico'),
]
TIPOS_EVENTO = ['Ataque con mordedura', 'Lesión compatible', 'Intento de ataque']
ENTES = ['Zoonosis', 'Policía']

# (nombre, apellido, edad, dni, teléfono, fecha, dirección, ciudad, especie, tamaño, lesión, organismo, estado, motivo, situación)
CASOS = [
    ('Joaquín', 'Ojeda', 12, '50111222', '2964-40-1111', '2026-09-06T11:15', 'San Martín 1502', 'Río Grande', 'perro', 'grande', 'mordedura', 'Hospital Regional RG', 'registrado', '', 'transito'),
    ('Micaela', 'Sosa', 7, '58412336', '2901-54-8820', '2026-09-12T13:50', 'Kuanip al 1200', 'Ushuaia', 'perro', 'mediano', 'mordedura', 'Hospital Regional Ushuaia', 'registrado', '', 'transito'),
    ('Héctor', 'Maldonado', 52, '20333444', '2901-44-0003', '2026-08-22T13:25', 'Rivadavia 610', 'Ushuaia', 'perro', 'grande', 'compatible', 'CAPS 4', 'desestimado', '', 'transito'),
    ('Sofía', 'Ledesma', 23, '38999000', '2901-44-0004', '2026-08-18T07:45', 'Maipú 1180', 'Ushuaia', 'perro', 'chico', 'mordedura', 'Zoonosis Ushuaia', 'registrado', '', 'laboral'),
    ('Valentina', 'Núñez', 8, '56777888', '2901-44-0005', '2026-08-27T16:55', 'Karukinká 540', 'Tolhuin', 'perro', 'mediano', 'mordedura', 'CAPS 5', 'finalizado', '', 'recreativa'),
    ('Tomás', 'Aguirre', 45, '28111333', '2964-40-0006', '2026-09-01T08:30', 'Alem 2190', 'Río Grande', 'perro', 'mediano', 'mordedura', 'Hospital Regional RG', 'en_seguimiento', 'contacto', ''),
    ('Elena', 'Quintana', 61, '14555666', '2901-44-0007', '2026-09-04T20:10', 'Magallanes 77', 'Ushuaia', 'gato', 'chico', 'aranazo', 'Zoonosis Ushuaia', 'registrado', '', 'domestica'),
    ('Lucía', 'Ferreyra', 29, '36222111', '2964-40-0008', '2026-09-09T18:40', 'Perito Moreno 320', 'Río Grande', 'perro', 'chico', 'compatible', 'CAPS 3', 'registrado', '', 'transito'),
    ('Nicolás', 'Vera', 41, '30123456', '2901-44-0009', '2026-09-11T10:40', 'Gobernador Paz 845', 'Ushuaia', 'perro', 'grande', 'mordedura', 'Hospital Regional Ushuaia', 'registrado', '', 'transito'),
    ('Ramiro', 'Beltrán', 34, '33987654', '2901-44-0010', '2026-09-11T09:05', 'Gobernador Paz 845', 'Ushuaia', 'perro', 'grande', 'mordedura', 'Zoonosis Ushuaia', 'en_seguimiento', 'certificado', 'transito'),
    # Se carga al final: coincide en teléfono y fecha con el de Micaela Sosa → queda "posible duplicado" e incompleto.
    ('Micaela', 'Sosa', 7, '58412336', '2901-54-8820', '2026-09-12T14:20', 'Kuanip 1240', 'Ushuaia', 'perro', 'mediano', 'mordedura', 'Zoonosis Ushuaia', 'registrado', '', ''),
]


class Command(BaseCommand):
    help = 'Carga catálogos y datos de ejemplo para desarrollo.'

    def add_arguments(self, parser):
        parser.add_argument('--clave', default='Siram-demo-2026', help='Clave de los usuarios de ejemplo.')
        parser.add_argument('--solo-catalogos', action='store_true', help='No crear usuarios ni casos.')

    @transaction.atomic
    def handle(self, *args, clave, solo_catalogos, **opciones):
        organismos = {n: Organismo.objects.get_or_create(nombre=n, defaults={'tipo': t})[0] for n, t in ORGANISMOS}
        tipo_evento = None
        for i, nombre in enumerate(TIPOS_EVENTO):
            obj, _ = TipoEvento.objects.get_or_create(nombre=nombre, defaults={'orden': i})
            tipo_evento = tipo_evento or obj
        for nombre in ENTES:
            EnteDenuncia.objects.get_or_create(nombre=nombre)
        self.stdout.write('Catálogos listos (organismos, tipos de evento, entes).')
        if solo_catalogos:
            return

        usuarios = {}
        definiciones = [
            ('admin', Usuario.Rol.ADMINISTRADOR, None, 'Ana', 'Administradora'),
            ('agente', Usuario.Rol.AGENTE, 'Zoonosis Ushuaia', 'Daniela', 'Marchisoney'),
            ('hospital', Usuario.Rol.AGENTE, 'Hospital Regional Ushuaia', 'Hugo', 'Herrera'),
            ('analista', Usuario.Rol.ANALISTA, 'CADIC', 'Alba', 'Analista'),
        ]
        for username, rol, organismo, nombre, apellido in definiciones:
            usuario, creado = Usuario.objects.get_or_create(
                username=username,
                defaults={'rol': rol, 'organismo': organismos.get(organismo), 'first_name': nombre,
                          'last_name': apellido, 'email': f'{username}@siram.local'},
            )
            if creado:
                usuario.set_password(clave)
                usuario.save()
            usuarios[username] = usuario
        self.stdout.write(f'Usuarios: {", ".join(usuarios)} (clave: {clave}).')

        if Caso.objects.exists():
            self.stdout.write('Ya hay casos cargados: no se agregan los de ejemplo.')
            return

        for (nombre, apellido, edad, dni, tel, fecha, direccion, ciudad, especie, tamano, lesion,
             org, estado, motivo, situacion) in CASOS:
            agente = next((u for u in usuarios.values() if u.organismo and u.organismo.nombre == org), None)
            if agente is None:  # organismos sin usuario propio: los carga el agente de Zoonosis a su nombre
                agente = usuarios['agente']
            momento = timezone.make_aware(datetime.fromisoformat(fecha))
            caso = servicios.crear_caso(
                agente,
                {
                    'victima': {'nombre': nombre, 'apellido': apellido, 'dni': dni, 'telefono': tel, 'edad_declarada': edad},
                    'tipo_evento': tipo_evento,
                    'fecha_hecho': momento,
                    'lugar_direccion': direccion,
                    'lugar_ciudad': ciudad,
                    'tipo_lugar': 'via_publica',
                    'situacion_persona': situacion or 'sin_dato',
                    'lesion': lesion,
                    'animales': [{'especie': especie, 'tamano': tamano, 'color': 'negro' if tamano == 'grande' else '',
                                  'tenencia': 'ajeno'}],
                },
                confirmar_duplicado=True,
            )
            if estado == Estado.EN_SEGUIMIENTO:
                servicios.cambiar_estado(agente, caso, Estado.EN_SEGUIMIENTO, motivo_espera=MotivoEspera(motivo))
            elif estado == Estado.FINALIZADO:
                servicios.cambiar_estado(agente, caso, Estado.FINALIZADO)
            elif estado == Estado.DESESTIMADO:
                servicios.cambiar_estado(agente, caso, Estado.DESESTIMADO, motivo='Datos insuficientes para registrar')
        self.stdout.write(self.style.SUCCESS(f'{Caso.objects.count()} casos de ejemplo cargados.'))
