"""R.27 (CSV/XLSX) y R.28 (PDF del caso)."""

import csv
import io
from xml.sax.saxutils import escape

from .models import Animal, Caso
from .utiles import iniciales

COLUMNAS = [
    'caso', 'fecha_hecho', 'estado', 'motivo_espera', 'organismo', 'tipo_evento', 'ciudad', 'tipo_lugar',
    'situacion_persona', 'lesion', 'zona_lesion', 'gravedad', 'atencion_medica', 'victima_iniciales',
    'victima_edad', 'victima_sexo', 'especie', 'tamano', 'tenencia', 'vacunado', 'castrado', 'identificado',
    'hizo_denuncia', 'incompleto', 'latitud_aprox', 'longitud_aprox',
]


def _celda(valor):
    """Evita la inyección de fórmulas al abrir el CSV/XLSX en una planilla."""
    if valor is None:
        return ''
    texto = str(valor)
    if texto and texto[0] in '=+-@\t\r':
        return "'" + texto
    return texto


def _redondear(valor):
    return '' if valor is None else round(float(valor), 3)  # ~100 m: útil para análisis, no señala un domicilio


def filas(queryset):
    """Una fila por caso. Por diseño NO incluye datos identificatorios (DNI, teléfono, nombre completo,
    domicilio): las exportaciones son para análisis del comité, no para circular datos personales."""
    queryset = queryset.select_related('victima', 'organismo', 'tipo_evento').prefetch_related('animales')
    for caso in queryset.iterator(chunk_size=500):
        animales = list(caso.animales.all())
        animal = animales[0] if animales else None
        yield [
            caso.numero,
            caso.fecha_hecho.isoformat(timespec='minutes') if caso.fecha_hecho else '',
            caso.get_estado_display(),
            caso.get_motivo_espera_display() if caso.motivo_espera else '',
            caso.organismo.nombre,
            caso.tipo_evento.nombre if caso.tipo_evento else '',
            caso.lugar_ciudad,
            caso.get_tipo_lugar_display(),
            caso.get_situacion_persona_display(),
            caso.get_lesion_display(),
            caso.lesion_localizacion,
            caso.get_lesion_gravedad_display(),
            caso.get_atencion_medica_display(),
            iniciales(caso.victima.nombre_completo),
            caso.victima.edad_al(caso.fecha_hecho) if caso.victima.edad_al(caso.fecha_hecho) is not None else '',
            caso.victima.get_sexo_display(),
            animal.get_especie_display() if animal else '',
            animal.get_tamano_display() if animal else '',
            animal.get_tenencia_display() if animal else '',
            animal.get_vacunado_display() if animal else '',
            animal.get_castrado_display() if animal else '',
            ('Sí' if animal.identificacion else 'No') if animal else '',
            caso.get_hizo_denuncia_display(),
            'Sí' if caso.incompleto else 'No',
            _redondear(caso.latitud),
            _redondear(caso.longitud),
        ]


def a_csv(queryset):
    salida = io.StringIO()
    salida.write('﻿')  # para que Excel reconozca los acentos
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(COLUMNAS)
    for fila in filas(queryset):
        escritor.writerow([_celda(v) for v in fila])
    return salida.getvalue().encode('utf-8')


def a_xlsx(queryset):
    from openpyxl import Workbook

    libro = Workbook(write_only=True)
    hoja = libro.create_sheet('Casos')
    hoja.append(COLUMNAS)
    for fila in filas(queryset):
        hoja.append([_celda(v) if isinstance(v, str) else v for v in fila])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def ficha_pdf(caso):
    """Documento del caso para presentar ante organismos externos. Incluye datos personales: solo para agentes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    estilos = getSampleStyleSheet()
    elementos = [Paragraph(f'SIRAM — Caso {escape(caso.numero)}', estilos['Title'])]

    def bloque(titulo, filas_):
        elementos.append(Paragraph(escape(titulo), estilos['Heading3']))
        tabla = Table([[Paragraph(f'<b>{escape(k)}</b>', estilos['BodyText']), Paragraph(escape(str(v or '—')), estilos['BodyText'])] for k, v in filas_], colWidths=[5 * cm, 11 * cm])
        tabla.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.25, colors.grey), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 8))

    v = caso.victima
    bloque('Caso', [
        ('Estado', caso.get_estado_display()),
        ('Registrado por', f'{caso.registrado_por.nombre_completo} ({caso.organismo.nombre})'),
        ('Fecha de registro', caso.creado_en.strftime('%d/%m/%Y %H:%M')),
        ('Tipo de evento', caso.tipo_evento.nombre if caso.tipo_evento else ''),
    ])
    bloque('Persona afectada', [
        ('Nombre', v.nombre_completo), ('DNI', v.dni), ('Edad', v.edad_al(caso.fecha_hecho)),
        ('Sexo', v.get_sexo_display()), ('Teléfono', v.telefono), ('Domicilio', f'{v.direccion} {v.ciudad}'.strip()),
    ])
    bloque('Hecho', [
        ('Fecha y hora', caso.fecha_hecho.strftime('%d/%m/%Y %H:%M') if caso.fecha_hecho else ''),
        ('Lugar', f'{caso.lugar_direccion}, {caso.lugar_ciudad}'.strip(', ')),
        ('Tipo de lugar', caso.get_tipo_lugar_display()), ('Situación', caso.get_situacion_persona_display()),
    ])
    bloque('Lesión', [
        ('Tipo', caso.get_lesion_display()), ('Zona', caso.lesion_localizacion),
        ('Gravedad', caso.get_lesion_gravedad_display()), ('Atención médica', caso.get_atencion_medica_display()),
    ])
    for i, a in enumerate(Animal.objects.filter(caso=caso), start=1):
        bloque(f'Animal {i}', [
            ('Especie', a.get_especie_display()), ('Tamaño', a.get_tamano_display()), ('Raza / color', f'{a.raza} {a.color}'.strip()),
            ('Tenencia', a.get_tenencia_display()), ('Vacunación antirrábica', a.get_vacunado_display()),
            ('Chip / identificación', a.identificacion), ('Tenedor responsable', a.tenedor_nombre),
        ])
    denuncias = [(d.ente.nombre, f'N° {d.numero or "s/n"} — {d.fecha.strftime("%d/%m/%Y") if d.fecha else "sin fecha"}') for d in caso.denuncias.select_related('ente')]
    bloque('Denuncias anotadas', denuncias or [('¿Hizo denuncia?', caso.get_hizo_denuncia_display())])
    if caso.observaciones:
        bloque('Observaciones', [('', caso.observaciones)])

    salida = io.BytesIO()
    SimpleDocTemplate(salida, pagesize=A4, title=f'Caso {caso.numero}').build(elementos)
    return salida.getvalue()
