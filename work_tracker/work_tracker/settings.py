from pathlib import Path
import os
import environ

# Base
BASE_DIR = Path(__file__).resolve().parent.parent

# Env
env = environ.Env(DEBUG=(bool, False))
ENV_FILE = BASE_DIR.parent / ".env"
if ENV_FILE.exists():
    env.read_env(str(ENV_FILE))

USE_S3_MEDIA = env("USE_S3_MEDIA", default="0") == "1"

# Security
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)  # nastav v .env (True/False)
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
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "tracker",
]

if USE_S3_MEDIA:
    INSTALLED_APPS.append("storages")

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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
STATICFILES_STORAGE = "whitenoise.storage.ManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "work_photos"

# === Media storage ===
if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="arbomap-media")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="eu-west-1")

    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=300)
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}

    AWS_MEDIA_PREFIX = env("AWS_MEDIA_PREFIX", default="").strip("/")
    if AWS_MEDIA_PREFIX:
        DEFAULT_FILE_STORAGE = "work_tracker.storage_backends.PrefixedMediaStorage"
    else:
        DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

    MEDIA_URL = (
        f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    )

# Defaults
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sites / allauth
# Domain spravujte v Django Admin → Sites: /admin/sites/site/1/change/ (např. moraviatrees.cz, název ArboMap)
# Po migracích spusťte: python manage.py ensure_site
SITE_ID = 1

# Auth backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Allauth settings
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_PREVENT_ENUMERATION = False
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[ArboMap] "
ACCOUNT_FORMS = {
    "signup": "tracker.forms.CustomSignupForm",
    "login": "tracker.forms.CustomLoginForm",
    "reset_password": "tracker.forms.CustomResetPasswordForm",
}
ACCOUNT_ADAPTER = "tracker.adapters.CustomAccountAdapter"

# Email
# Mailtrap SMTP tip: EMAIL_HOST=live.smtp.mailtrap.io, EMAIL_HOST_USER=api, EMAIL_HOST_PASSWORD=<api_token>
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = str(os.environ.get("EMAIL_USE_TLS", "1")).lower() in ("1", "true", "yes")
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")
    SERVER_EMAIL = os.environ.get("SERVER_EMAIL", "webmaster@localhost")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "work_record_list"
LOGIN_REDIRECT_URL = "work_record_list"
