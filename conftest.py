"""Configure Django before test collection (the suite has no pytest-django)."""

import os

import django
import pytest
from django.conf import settings
from django.test.utils import setup_databases, teardown_databases

if not settings.configured:
    # Assigned, not setdefault()-ed: a DJANGO_SETTINGS_MODULE exported in the shell for
    # some other project would otherwise be picked up and break collection outright.
    os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
    django.setup()


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Create real tables for TransactionTestCase without adding pytest-django."""
    config = setup_databases(verbosity=0, interactive=False)
    yield
    teardown_databases(config, verbosity=0)
