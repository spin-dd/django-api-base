from django.contrib.contenttypes.models import ContentType
from django.template import loader

from apibase.utils import query, to_gql_relay_id

from .utils import strip_relay


def query_model_file(model_or_instance, name=None, object_name=None, id=None, **params):
    """
    Use .graphql files under django standard templates directories
    default:
        - query.graphql:  id is specifiled
        - query_set.graphql: id is not specified
    """
    if isinstance(model_or_instance, str):
        model_or_instance = ContentType.objects.get_by_natural_key(*model_or_instance.split(".")).model_class()

    opt = model_or_instance._meta
    object_name = object_name or opt.object_name
    if id or isinstance(model_or_instance, opt.model):
        name = name or "query"
        id = id or model_or_instance.id
    else:
        name = name or "query_set"

    template = f"{opt.app_label}/{opt.model_name}/{name}.graphql"
    return loader.get_template(template).template.source


def query_model(model_or_instance, name=None, object_name=None, id=None, strip=True, **params):
    """
    Use .graphql files under django standard templates directories
    default:
        - query.graphql:  id is specifiled
        - query_set.graphql: id is not specified
    """
    if isinstance(model_or_instance, str):
        model_or_instance = ContentType.objects.get_by_natural_key(*model_or_instance.split(".")).model_class()

    opt = model_or_instance._meta
    object_name = object_name or opt.object_name
    id = id or (isinstance(model_or_instance, opt.model) and model_or_instance.id)

    source = query_model_file(model_or_instance, name=name, object_name=object_name, id=id, **params)

    data = query(source, object_name=object_name, id=id, **params)
    return strip and strip_relay(data, recursive=True) or data


def query_params(model_or_instance, name=None, object_name=None, id=None, **params):
    if isinstance(model_or_instance, str):
        model_or_instance = ContentType.objects.get_by_natural_key(*model_or_instance.split(".")).model_class()

    source = query_model_file(model_or_instance, name=name, object_name=object_name, id=id, **params)
    vars = dict(**params)
    if id:
        vars["id"] = to_gql_relay_id(model_or_instance._meta.object_name, id)
    return dict(
        query=source,
        variables=vars,
    )
