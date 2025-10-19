from pathlib import Path
import os
import environ

# Base
BASE_DIR = Path(__file__).resolve().parent.parent

# Env
env = environ.Env(
    DEBUG=(bool, True),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# Security
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")  # nastavíš v .env (True/False)
MAPY_API_KEY = env("MAPY_API_KEY", default="")

ALLOWED_HOSTS = [
    "129.159.223.132",
    "localhost",
    "127.0.0.1",
    "moraviatrees.cz",
    "www.moraviatrees.cz",
    "10.0.0.242",
]



CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "http://129.159.223.132",
        "https://129.159.223.132",
        "http://moraviatrees.cz",
        "https://moraviatrees.cz",
        "http://www.moraviatrees.cz",
        "https://www.moraviatrees.cz",
    ],
)
# Apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tracker",
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "work_tracker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "work_tracker.wsgi.application"

# Database (výchozí SQLite; můžeš přepsat přes DATABASE_URL v .env)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
if env("DATABASE_URL", default=None):
    DATABASES = {"default": env.db("DATABASE_URL")}

# Password validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# I18N
LANGUAGE_CODE = "cs"
TIME_ZONE = "Europe/Prague"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]  # může klidně dočasně neexistovat
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Defaults
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "work_record_list"
LOGIN_REDIRECT_URL = "work_record_list"
