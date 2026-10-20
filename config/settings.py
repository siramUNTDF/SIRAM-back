import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env(nombre, defecto=None):
    return os.environ.get(nombre, defecto)


def env_bool(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ('1', 'true', 'si', 'sí', 'yes')


def env_lista(nombre, defecto=''):
    return [x.strip() for x in env(nombre, defecto).split(',') if x.strip()]


DEBUG = env_bool('DJANGO_DEBUG', False)
USA_POSTGRES = bool(env('POSTGRES_DB'))

SECRET_KEY = env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'insegura-solo-para-desarrollo-no-usar-en-produccion-0123456789'
    else:
        raise ImproperlyConfigured('Falta DJANGO_SECRET_KEY (copiá .env.example a .env).')

ALLOWED_HOSTS = env_lista('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'apps.accounts',
    'apps.casos',
]

if USA_POSTGRES:
    # unaccent / pg_trgm para la búsqueda sin tildes (ver migración casos.0002_unaccent).
    INSTALLED_APPS.insert(INSTALLED_APPS.index('rest_framework'), 'django.contrib.postgres')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

if USA_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('POSTGRES_DB'),
            'USER': env('POSTGRES_USER', 'siram'),
            'PASSWORD': env('POSTGRES_PASSWORD', ''),
            'HOST': env('POSTGRES_HOST', 'localhost'),
            'PORT': env('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': int(env('POSTGRES_CONN_MAX_AGE', '60')),
        }
    }
else:
    # Solo desarrollo y tests: sin POSTGRES_DB se usa SQLite.
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'accounts.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Ushuaia'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Los adjuntos (certificados médicos, fotos) son datos sensibles: no se sirven como estáticos.
MEDIA_ROOT = Path(env('MEDIA_ROOT', str(BASE_DIR / 'media')))
DATA_UPLOAD_MAX_MEMORY_SIZE = 12582912

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- API REST -----------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['djangorestframework_camel_case.render.CamelCaseJSONRenderer'],
    'DEFAULT_PARSER_CLASSES': [
        'djangorestframework_camel_case.parser.CamelCaseJSONParser',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'apps.casos.paginacion.PaginacionEstandar',
    'PAGE_SIZE': 25,
    'COERCE_DECIMAL_TO_STRING': False,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_RATES': {'login': '10/min'},
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'SIRAM API',
    'DESCRIPTION': 'Sistema Integrado de Registro de Ataques y Mordeduras — API REST (contrato del front).',
    'VERSION': '0.1.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.contrib.djangorestframework_camel_case.camelize_serializer_fields',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(env('JWT_ACCESS_MINUTOS', '30'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(env('JWT_REFRESH_DIAS', '1'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

# --- CORS / HTTPS ---------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_lista('CORS_ALLOWED_ORIGINS', 'http://localhost:5173')
CSRF_TRUSTED_ORIGINS = env_lista('CSRF_TRUSTED_ORIGINS', 'http://localhost:5173')

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL', False)
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL_REDIRECT else 0
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

# --- Políticas de SIRAM (puntos pendientes de definir con los organismos) ---------
SIRAM_2FA_OBLIGATORIO = env_bool('SIRAM_2FA_OBLIGATORIO', False)

SIRAM_EDICION_ENTRE_ORGANISMOS = env_bool('SIRAM_EDICION_ENTRE_ORGANISMOS', True)

SIRAM_VENTANA_DUPLICADOS_DIAS = int(env('SIRAM_VENTANA_DUPLICADOS_DIAS', '7'))

SIRAM_DIRECTORIO_RESPALDOS = Path(env('SIRAM_DIRECTORIO_RESPALDOS', str(BASE_DIR / 'respaldos')))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'consola': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['consola'], 'level': 'INFO'},
}
