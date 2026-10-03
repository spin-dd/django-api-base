"""Minimal Django settings for the test suite.

The root conftest creates in-memory SQLite databases for the transactional
serializer and batch API tests. The tests app has no migrations.
"""

SECRET_KEY = "test"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "other": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
