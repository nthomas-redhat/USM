"""
Django settings for usm project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 't9%h9+f239em^gr_(f3^y_xk08#hp7p4g0ylqxu972^=eshr6*'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = (
    #'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'usm_rest_api',
    'rest_framework',
    'djcelery',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'usm.urls'

WSGI_APPLICATION = 'usm.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'usm',
        'USER': 'usm',
        'PASSWORD': 'usm',
        'HOST': '127.0.0.1',
        'PORT': '',
        
    }
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication'
    ),

    # Use hyperlinked styles by default.
    # Only used if the `serializer_class` attribute is not set on a view.
    #'DEFAULT_MODEL_SERIALIZER_CLASS':
    #'rest_framework.serializers.HyperlinkedModelSerializer',

    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated'
    ],
    
}

# CELERY SETTINGS
BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_IMPORTS=("usm_rest_api.v1.views.views")
CELERY_RESULT_BACKEND = 'redis://127.0.0.1/0'

import djcelery
djcelery.setup_loader()


#LOGGING CONFIGURATION
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': "%(asctime)s - %(levelname)s - %(name)s %(message)s"
        }
    },
    'handlers': {
        'django_logging': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/usm/usm.log',
            'maxBytes': 1024*1024*5, #5MB
            "backupCount": 10,
            'formatter': 'standard'
        },
        'request_logging': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/usm/usm_request.log',
            'maxBytes': 1024*1024*5, #5MB
            "backupCount": 10,
            'formatter': 'standard'
        },
        'db_logging': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/usm/usm_db.log',
            'maxBytes': 1024*1024*5, #5MB
            "backupCount": 10,
            'formatter': 'standard'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['django_logging'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['request_logging'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django.db': {
            'handlers': ['db_logging'],
            'level': 'DEBUG',
            'propagate': False,
        },
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

STATIC_URL = '/static/'
