import json

import graphene.relay
from django.db.models import QuerySet
from graphene.types import generic

from .. import serializers
from .encoders import JSONEncode


class NodeMixin:
    # self: Model Class

    pk = graphene.Int()
    endpoint = graphene.String()
    urn = graphene.String()
    display = graphene.String()

    def resolve_pk(self, info):
        return self.pk

    def resolve_endpoint(self, info):
        path = serializers.drf_endpoint(self)
        if hasattr(info.context, "build_absolute_uri"):
            return info.context.build_absolute_uri(path)
        return path

    def resolve_urn(self, info):
        return serializers.to_urn(self)

    def resolve_display(self, info):
        return str(self)

    @classmethod
    def get_node(cls, info, id):
        queryset = cls.get_queryset(cls._meta.model.objects, info)
        try:
            return queryset.get(pk=id)
        except cls._meta.model.DoesNotExist:
            return None


class SummaryMixin:
    total_count = graphene.Int()
    records = graphene.Int()
    summary = generic.GenericScalar()

    def resolve_total_count(self, info, **kwargs):
        return self.length

    def resolve_summary(self, info, **kwargs):
        if isinstance(self.iterable, QuerySet) and hasattr(self.iterable, "summary"):
            data = json.dumps(self.iterable.summary(), cls=JSONEncode)
            return json.loads(data)
        return None

    def resolve_records(self, info, **kwargs):
        if isinstance(self.iterable, QuerySet):
            # TODO: each models may have it own countable criteria
            return self.iterable.order_by("id").distinct().count()

        return self.length
