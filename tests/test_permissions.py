"""Tests for `IsAuthenticatedOrOptions` and the `_decorate` stack that uses it.

No database is needed: `is_authenticated` is True for an unsaved `User` instance,
so `force_authenticate` can stand in for a real session without a write.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser, User
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apibase.permissions import IsAuthenticatedOrOptions
from apibase.views import _decorate


@_decorate
def _view(request):
    """Stand-in for the real GraphQL/SDL views, wrapped in the same decorators."""
    return Response({"reached": True})


@pytest.fixture
def factory():
    return APIRequestFactory()


def test_options_needs_no_credentials(factory):
    """The regression: DRF runs check_permissions before it routes OPTIONS."""
    response = _view(factory.options("/"))
    assert response.status_code == 200


def test_options_returns_metadata_not_the_handler(factory):
    """OPTIONS is answered by APIView.options, so the wrapped view never runs."""
    response = _view(factory.options("/"))
    assert "reached" not in response.data
    assert set(response.data) == {"name", "description", "renders", "parses"}


@pytest.mark.parametrize("method", ["get", "post"])
def test_other_methods_still_need_credentials(factory, method):
    response = _view(getattr(factory, method)("/"))
    # 403 rather than 401 under the default authenticators: SessionAuthentication
    # returns no WWW-Authenticate header, so DRF coerces NotAuthenticated to 403.
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("method", ["get", "post"])
def test_other_methods_pass_when_authenticated(factory, method):
    request = getattr(factory, method)("/")
    force_authenticate(request, user=User(username="someone"))
    response = _view(request)
    assert response.status_code == 200
    assert response.data == {"reached": True}


@pytest.mark.parametrize(
    ("method", "user", "expected"),
    [
        ("OPTIONS", AnonymousUser(), True),
        ("OPTIONS", User(username="someone"), True),
        ("GET", AnonymousUser(), False),
        ("GET", User(username="someone"), True),
        ("POST", AnonymousUser(), False),
    ],
)
def test_has_permission(method, user, expected):
    request = SimpleNamespace(method=method, user=user)
    assert IsAuthenticatedOrOptions().has_permission(request, view=None) is expected
