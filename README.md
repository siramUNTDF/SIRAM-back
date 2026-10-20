# SIRAM — backend

API REST (Django + Django REST Framework) de **SIRAM**, el Sistema Integrado de Registro de Ataques y
Mordeduras. Es el backend del front <https://github.com/dddarioDLC/siram-front> (React + Vite + MUI).

El front es la fuente de la narrativa de uso (`docs/narrativa.md` de ese repo). Donde el PDF de requisitos
y el front difieren, **se siguió al front**: no hay formulario público ni cola de validación, la denuncia vive
dentro del caso y los estados son cinco.

## Puesta en marcha (desarrollo)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # sin POSTGRES_DB usa SQLite
python manage.py migrate
python manage.py cargar_demo    # catálogos, usuarios y casos de ejemplo (solo desarrollo)
python manage.py runserver      # http://localhost:8000  ·  docs: /api/docs/  ·  esquema: /api/schema/
python manage.py test           # 54 tests
```

Usuarios de ejemplo (clave `Siram-demo-2026`): `admin`, `agente` (Zoonosis), `hospital`, `analista`.

Con **PostgreSQL**: definir `POSTGRES_*` en `.env`. La búsqueda sin tildes (`nunez` → «Núñez») usa la extensión
`unaccent` (la crea la migración `casos.0002`); en SQLite distingue tildes.

## Conectar el front

1. En `siram-front/vite.config.js` agregar el proxy, así el front llama a `/api` sin CORS:
   `server: { proxy: { '/api': 'http://localhost:8000' } }`
2. Reemplazar `src/mocks/index.js` por llamadas a la API. `GET /api/casos/` devuelve **la misma forma que
   `src/mocks/casos.js`** (`id`, `fechaHecho`, `victima`, `lugar`, `animal`, `lesion`, `estado`, `motivoEspera`,
   `unificadoEn`, `origen`, `marcas`), paginado: `{ count, next, previous, results }`.
3. `POST /api/auth/login/` devuelve `access` y `refresh` (JWT); enviar `Authorization: Bearer <access>`.
   Las claves JSON van en camelCase, y los parámetros de consulta en snake_case (`motivo_espera`, `page_size`).

## Endpoints principales

| Área | Endpoints |
|---|---|
| Sesión | `auth/login`, `auth/refresh`, `auth/logout`, `auth/yo`, `auth/2fa/{configurar,activar,desactivar}` |
| Casos | `casos/` (alta/lista), `casos/{C-2026-0418}/` (ficha/edición), `…/cambiar-estado`, `…/desestimar`, `…/auditoria`, `…/animales`, `…/denuncias`, `…/documentos`, `…/seguimientos`, `…/ficha-pdf`, `casos/contadores/` |
| Duplicados | `coincidencias/`, `coincidencias/{id}/` y `consolidar`, `vincular`, `desvincular`, `descartar` |
| Consultas | `inicio/`, `consultas/estadisticas/`, `consultas/exportar/` (CSV/XLSX), `opciones/` (catálogos) |
| Administración | `usuarios/`, `organismos/`, `tipos-evento/`, `entes/` |

Filtros de `casos/`: `q`, `estado`, `motivo_espera`, `marca` (`incompleto|duplicado|relacionado`, solo vigentes),
`vigentes`, `organismo`, `tipo_evento`, `lesion`, `tipo_lugar`, `especie`, `ciudad`, `desde`, `hasta`.
Los chips de la Bandeja equivalen a `marca=…` o `estado=en_seguimiento`; los contadores salen de `casos/contadores/`.

## Reglas importantes

- **No se borra nada**: no hay `DELETE` de casos. Desestimar exige motivo; consolidar es irreversible y nunca
  automático; los eventos relacionados solo se vinculan (reversible).
- **Auditoría** de cada cambio (quién, cuándo, qué), incluido «Sistema».
- **Datos personales** (DNI, teléfono, domicilio, adjuntos médicos) se ocultan en el servidor según rol y organismo.
- Roles: administrador (usuarios y catálogos), agente interno (carga y edita casos), analista (solo consulta).
- Doble factor TOTP opcional por usuario; `SIRAM_2FA_OBLIGATORIO=true` lo exige a todos.

## Operación

- `python manage.py respaldar [--retener 14]` — copia de la base (R.31); programarlo con cron. Los adjuntos
  (`MEDIA_ROOT`) se copian aparte.
- Docker (RT.05): `cp .env.example .env`, completar `DJANGO_SECRET_KEY` y `POSTGRES_PASSWORD`,
  `docker compose up --build`. Nginx hace de reverse proxy; para HTTPS ver `nginx/default.conf`.

## Pendiente o por definir con los organismos

- Formulario público (R.17), importación CSV (R.25), mapa y «fecha de novedad»: el front los marca como
  pendientes; **no están implementados**.
- Criterio para pasar a *Finalizado*, lista de motivos para desestimar y valores de «Tipo de evento»: hoy son
  texto libre / catálogo editable.
- ¿Un agente puede editar casos de otro organismo? Hoy sí (`SIRAM_EDICION_ENTRE_ORGANISMOS=true`).
- Georreferenciación (RT.06): se guardan `latitud`/`longitud`; PostGIS no está incorporado.
