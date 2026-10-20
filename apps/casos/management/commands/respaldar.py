"""Copia de seguridad de la base de datos (R.31).

Uso:  python manage.py respaldar [--retener 14]
Genera un archivo con fecha en SIRAM_DIRECTORIO_RESPALDOS y borra los más viejos. Pensado para correr
desde cron / un job programado. Con PostgreSQL usa pg_dump (formato custom: se restaura con pg_restore);
con SQLite copia el archivo. Los adjuntos (MEDIA_ROOT) se respaldan aparte, copiando esa carpeta.
"""
import os
import shutil
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Genera una copia de seguridad de la base de datos.'

    def add_arguments(self, parser):
        parser.add_argument('--retener', type=int, default=14, help='Cantidad de copias a conservar.')

    def handle(self, *args, retener, **opciones):
        destino = settings.SIRAM_DIRECTORIO_RESPALDOS
        destino.mkdir(parents=True, exist_ok=True)
        sello = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        bd = settings.DATABASES['default']

        if bd['ENGINE'].endswith('postgresql'):
            archivo = destino / f'siram-{sello}.dump'
            entorno = dict(os.environ, PGPASSWORD=str(bd.get('PASSWORD') or ''))
            comando = ['pg_dump', '-Fc', '-h', str(bd.get('HOST') or 'localhost'), '-p', str(bd.get('PORT') or 5432),
                       '-U', str(bd['USER']), '-f', str(archivo), str(bd['NAME'])]
            try:
                subprocess.run(comando, check=True, env=entorno)
            except FileNotFoundError as exc:
                raise CommandError('No se encontró pg_dump en el PATH.') from exc
            except subprocess.CalledProcessError as exc:
                archivo.unlink(missing_ok=True)
                raise CommandError(f'pg_dump falló (código {exc.returncode}).') from exc
        elif bd['ENGINE'].endswith('sqlite3'):
            archivo = destino / f'siram-{sello}.sqlite3'
            shutil.copy2(bd['NAME'], archivo)
        else:
            raise CommandError(f'Motor no soportado: {bd["ENGINE"]}')

        archivo.chmod(0o600)  # contiene datos personales y de salud
        copias = sorted(destino.glob('siram-*'), key=lambda p: p.stat().st_mtime, reverse=True)
        for vieja in copias[max(retener, 1):]:
            vieja.unlink()
        self.stdout.write(self.style.SUCCESS(f'Copia creada: {archivo}'))
