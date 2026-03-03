"""
Django settings for cisis project.

Секреты (пароли, ключи) читаются из файла .env в корне проекта.
Файл .env НЕ попадает в Git — у каждого окружения свой.
Шаблон: .env.example
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из корня проекта
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


# ---------------------------------------------------------------------
# БЕЗОПАСНОСТЬ
# ---------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-for-local-dev')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()
]


# ---------------------------------------------------------------------
# ПРИЛОЖЕНИЯ
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cisis.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'core' / 'templates',
            BASE_DIR / 'templates',
        ],
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

WSGI_APPLICATION = 'cisis.wsgi.application'


# ---------------------------------------------------------------------
# БАЗА ДАННЫХ
# ---------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'CISIS'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}


# ---------------------------------------------------------------------
# ВАЛИДАЦИЯ ПАРОЛЕЙ
# ---------------------------------------------------------------------
# Отключена — используется собственная модель User с кастомным
# хешированием паролей.
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = []


# ---------------------------------------------------------------------
# ИНТЕРНАЦИОНАЛИЗАЦИЯ
# ---------------------------------------------------------------------
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------
# СТАТИКА И МЕДИА
# ---------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media'))

# Максимальный размер загружаемого файла (1 ГБ)
FILE_UPLOAD_MAX_MEMORY_SIZE = 1073741824
DATA_UPLOAD_MAX_MEMORY_SIZE = 1073741824

ALLOWED_FILE_EXTENSIONS = [
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.rtf',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff',
    '.mp4', '.avi', '.mov', '.mkv', '.wmv',
    '.zip', '.rar', '.7z',
]


# ---------------------------------------------------------------------
# АУТЕНТИФИКАЦИЯ
# ---------------------------------------------------------------------
AUTH_USER_MODEL = 'core.User'

AUTHENTICATION_BACKENDS = [
    'core.auth_backend.CustomUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = '/admin/login/'
# LOGIN_URL = '/workspace/login/'
LOGIN_REDIRECT_URL = '/workspace/'