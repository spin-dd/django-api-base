import rest_framework
from django.http import HttpResponse
from graphene_django import settings, views
from graphql.utils import schema_printer
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.settings import api_settings


def _decorate(view):
    view = permission_classes((IsAuthenticated,))(view)
    view = authentication_classes(api_settings.DEFAULT_AUTHENTICATION_CLASSES)(view)
    return api_view(["GET", "POST"])(view)


class DRFAuthenticatedGraphQLView(views.GraphQLView):
    def parse_body(self, request):
        if isinstance(request, rest_framework.request.Request):
            return request.data
        return super().parse_body(request)

    @classmethod
    def as_view(cls, *args, **kwargs):
        return _decorate(super().as_view(*args, **kwargs))


@_decorate
def sdl(request):
    """GraphQL Schema Definition Language (SDL)."""
    schema_str = schema_printer.print_schema(settings.graphene_settings.SCHEMA)
    return HttpResponse(schema_str, content_type="text/plain")
