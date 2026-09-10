"""Minimal Django settings for the test suite.

`tests/models.py` only needs a configured app registry — the filter tests apply
filters to lazy querysets and never hit the database, so the sqlite entry exists
just to satisfy Django's checks.
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
    }
}

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
