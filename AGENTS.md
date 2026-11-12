# Trabajo en SIRAM-back

## Contexto y alcance

API REST de SIRAM en Django/DRF para el registro compartido de ataques y mordeduras.
Consumidor: [siram-front](https://github.com/siramUNTDF/siram-front).
Dominio y decisiones: [siram-proyecto](https://github.com/siramUNTDF/siram-proyecto),
`CONTEXTO.md`, `modelo/decisiones.md`, `modelo/preguntas.md` y `modelo/siram.mmd`.
Leer instrucciones del directorio antes de editar. Conservar cambios ajenos.

El modelo v2 está declarado borrador sin tag; no afirmar que el backend lo implementa.
El código, migraciones y pruebas describen la implementación actual; los requisitos describen
el comportamiento esperado. Registrar sus diferencias; no cambiar requisitos para ocultarlas.
Ante conflictos de dominio, consultar las decisiones vigentes y registrar la duda en
`modelo/preguntas.md`; no inventar una regla. No modificar otros repos fuera del alcance autorizado.

## Mapa

- `config/`: configuración Django, URLs raíz, WSGI/ASGI.
- `apps/accounts/`: usuarios, organismos, JWT/TOTP, serializers y permisos por rol.
- `apps/casos/models.py`, `migrations/`: persistencia y evolución del esquema.
- `apps/casos/serializers.py`, `views.py`, `urls.py`: contrato y operaciones HTTP.
- `apps/casos/servicios/`: operaciones de negocio, transacciones, numeración, coincidencias,
  consolidación, marcas y auditoría.
- `apps/casos/consultas.py`, `filtros.py`, `exportes.py`: consultas y reportes.
- `apps/*/tests/`: pruebas Django/DRF; `management/commands/`: datos de demo y respaldos.
- `openspec/`: proceso SDD y cambios; [guía y plantilla](openspec/README.md).

## Comandos y entorno

Desde la raíz, en un checkout de desarrollo **aislado**:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Revisar .env localmente: DEBUG/clave y destino de base/archivos antes de continuar.
python manage.py check
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

En PowerShell, activar con `.venv\Scripts\Activate.ps1` y copiar el ejemplo con `Copy-Item`.
Sin `POSTGRES_DB` se usa `db.sqlite3` dentro del checkout; PostgreSQL usa `POSTGRES_*`.
Sin clave y con DEBUG desactivado Django no inicia. No imprimir valores de `.env`.
`cargar_demo` escribe catálogos, usuarios y casos: usarlo únicamente en una base descartable.

Verificaciones disponibles, después de revisar el aislamiento:

```bash
python manage.py test apps.accounts.tests
python manage.py test apps.casos.tests
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file /tmp/siram-schema.yaml --validate
git diff --check
```

El archivo temporal de esquema debe quedar fuera de Git (usar una ruta temporal equivalente
en Windows). Swagger y esquema HTTP: `/api/docs/` y `/api/schema/`.
**Estado al 2026-11-12:** comandos Django contrastados con `manage.py`, dependencias,
configuración y pruebas; no ejecutados en esta entrega documental. No equivalen a pruebas
aprobadas. `git diff --check` se ejecuta al revisar cada entrega. No hay validador documental
ni linter Python configurado en el repositorio al preparar esta guía.

## Código, API y datos

- Seguir el estilo existente: Python con cuatro espacios, funciones/variables en `snake_case`,
  clases en `PascalCase`, nombres de dominio y mensajes en español; agrupar imports como el módulo.
- Serializers para validar entradas, permisos en el servidor y servicios para operaciones de
  negocio; mantener transacciones y rastro de auditoría de las operaciones afectadas.
- Preservar rutas, métodos, códigos HTTP, JWT, JSON camelCase, parámetros de consulta snake_case
  y paginación mientras no se acuerde un cambio de contrato. Revisar consumidores y OpenAPI.
  Los mocks del front no prueban compatibilidad con la API actual.
- Explicitar cambios incompatibles y su transición en proposal/design; no renombrar ni eliminar
  campos silenciosamente. Mantener numeración, referencias y trazabilidad; casos sin DELETE.
- No reescribir migraciones ya compartidas ni perder datos. Cambios de esquema requieren
  migraciones incrementales y verificación en una copia descartable con datos representativos.

## Verificación proporcional y seguridad

Cambios de lógica: escenarios normales, límites y errores. API: contrato, autenticación,
permisos y recorte de datos. Persistencia: integridad, migraciones y reversión/recuperación
según corresponda. Operaciones transaccionales: rollback y concurrencia cuando sea relevante.
Ejecutar pruebas focalizadas y ampliar a la suite según impacto; no adaptar expectativas para
legitimar una contradicción con el dominio. SQLite no verifica `unaccent` de PostgreSQL.

Solo documentación: enlaces, coherencia y diff; no crear pruebas de existencia de Markdown.
No afirmar ejecución si solo se leyó código. Registrar comando, resultado y bloqueo.
No instalar herramientas ni cambiar dependencias, CI o despliegue fuera del alcance autorizado.
Los tests pueden crear una base de prueba y escribir adjuntos: usar credenciales exclusivas,
base de desarrollo descartable, `MEDIA_ROOT` y respaldos temporales; nunca bases compartidas.
No versionar secretos, tokens, volcados o datos personales; usar ejemplos ficticios.

## SDD, memoria y entrega

Seguir [openspec/README.md](openspec/README.md): comportamiento vigente en `specs/`, cambios
pendientes en `changes/`; registro simplificado para documentación o pruebas sin cambio funcional.
No exigir confirmaciones adicionales dentro de un alcance ya autorizado.
Cerrar cada cambio significativo o PR con un resumen en **`MEMORY.md` de siram-proyecto**.
Localizar ese repositorio por su remoto indicado arriba, aunque el checkout tenga otro nombre;
no depender de rutas absolutas ni crear otra memoria aquí. Si no está disponible, informar la
actualización pendiente con el resumen que deberá incorporarse.

Antes de entregar: revisar `git status`, diff completo y staged, excluir cambios ajenos y secretos;
comprobar criterios de aceptación y documentar límites, specs y memoria. Usar ramas por cambio,
commits `tipo(ámbito): descripción` en español y PR contra la base real. Verificar cuenta e identidad
de autor/committer; preservar firmas y atribuciones. Commit/push/PR solo con autorización vigente;
no push directo a base, force push, merge ni despliegue salvo instrucción explícita.

**Terminado:** alcance entregado, criterios demostrados, checks aplicables con evidencia,
compatibilidad/migraciones revisadas, especificaciones sincronizadas, memoria actualizada y diff
limpio de cambios ajenos. Un bloqueo se informa; no se marca como aprobado ni se archiva trabajo
incompleto. Distinguir implementación, verificación y publicación pendiente.
