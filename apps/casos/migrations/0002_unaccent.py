from django.db import migrations


def crear_extension(apps, schema_editor):
    # Solo PostgreSQL: permite buscar «Nicolás» escribiendo «nicolas». En SQLite no hace nada.
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('CREATE EXTENSION IF NOT EXISTS unaccent')


class Migration(migrations.Migration):
    dependencies = [('casos', '0001_initial')]
    operations = [migrations.RunPython(crear_extension, migrations.RunPython.noop)]
