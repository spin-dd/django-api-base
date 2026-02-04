from graphene.types import resolver

# https://docs.graphene-python.org/projects/django/en/latest/queries/
from graphene_django.rest_framework.mutation import SerializerMutation
from graphql_relay import from_global_id

from .graphql import fields, mixins


def default_resolver(attname, default_value, root, info, **args):
    """root: model instance, info:graphql.execution.base.ResolveInfo"""
    res = resolver.default_resolver(attname, default_value, root, info, **args)
    if hasattr(info.parent_type.graphene_type, "patch_result"):
        return info.parent_type.graphene_type.patch_result(res, attname, default_value, root, info, **args)
    return res


NodeMixin = mixins.NodeMixin
NodeSet = fields.NodeSet


class BaseSerializerMutation(SerializerMutation):
    class Meta:
        abstract = True

    @classmethod
    def get_serializer_kwargs(cls, root, info, **input):
        client_mutation_id = input.get("client_mutation_id", None)
        if isinstance(client_mutation_id, str):
            _, id = from_global_id(client_mutation_id)
            input["id"] = id
        return super().get_serializer_kwargs(root, info, **input)
