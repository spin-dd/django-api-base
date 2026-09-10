"""Configure Django before test collection (the suite has no pytest-django)."""

import os

import django
from django.conf import settings

if not settings.configured:
    # Assigned, not setdefault()-ed: a DJANGO_SETTINGS_MODULE exported in the shell for
    # some other project would otherwise be picked up and break collection outright.
    os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
    django.setup()
