# https://docs.graphene-python.org/projects/django/en/latest/queries/
from django_filters.utils import get_field_parts
from graphene_django.filter import DjangoFilterConnectionField

from .. import filters, utils
from .connections import FilteringConnection


def _filter_needs_distinct(filter_field, model):
    """Check if a filter requires distinct() based on explicit flag or M2M/reverse FK.

    Args:
        filter_field: A django_filters filter instance
        model: The Django model class

    Returns:
        True if the filter needs distinct(), False otherwise
    """
    # Layer 1: Explicit distinct flag
    if getattr(filter_field, "distinct", False):
        return True

    # Layer 2: Analyze field path for M2M or reverse FK relationships
    field_name = getattr(filter_field, "field_name", None)
    if field_name:
        try:
            field_parts = get_field_parts(model, field_name)
            for field in field_parts:
                if getattr(field, "many_to_many", False):
                    return True
                if getattr(field, "one_to_many", False):
                    return True
        except Exception:
            pass  # Field path analysis failed, continue to next layer

    return False


def _queryset_has_duplicating_joins(qs):
    """Fallback: Check QuerySet's alias_map for JOINs that could cause duplicates.

    Args:
        qs: A Django QuerySet

    Returns:
        True if the QuerySet has JOINs that could cause duplicate rows
    """
    try:
        from django.db.models.sql.datastructures import Join

        for _alias, join_info in qs.query.alias_map.items():
            if isinstance(join_info, Join) and join_info.join_field:
                join_field = join_info.join_field
                if getattr(join_field, "many_to_many", False):
                    return True
                if getattr(join_field, "one_to_many", False):
                    return True
        return False
    except Exception:
        return True  # Conservative fallback on error


def _needs_distinct(qs, args, filterset_class):
    """Determine if queryset needs distinct() applied.

    Args:
        qs: A Django QuerySet
        args: The GraphQL query arguments
        filterset_class: The FilterSet class (or None)

    Returns:
        True if distinct() should be applied, False otherwise
    """
    if not filterset_class:
        return False

    model = filterset_class._meta.model
    base_filters = filterset_class.base_filters

    # Find which filters are actually applied
    applied_filter_names = set(args.keys()) & set(base_filters.keys())

    if not applied_filter_names:
        return False  # No filters applied

    # Check each applied filter
    for filter_name in applied_filter_names:
        filter_field = base_filters[filter_name]
        if _filter_needs_distinct(filter_field, model):
            return True

    # Fallback: Check QuerySet JOINs
    return _queryset_has_duplicating_joins(qs)


class NodeSet(DjangoFilterConnectionField):
    # https://github.com/graphql-python/graphene-django/issues/320#issuecomment-404802724

    def __init__(self, *args, **kwargs):
        name_prefix = kwargs.pop("name_prefix", "")
        super().__init__(*args, **kwargs)
        self.name_prefix = name_prefix

    @property
    def type(self):
        class NodeSetConnection(FilteringConnection):
            class Meta:
                node = self._type
                name = f"{self.name_prefix}{self._type._meta.name}NodeSetConnection"

        return NodeSetConnection

    @classmethod
    def resolve_connection(cls, connection, args, iterable, *nargs, **kwargs):
        # connectioon: NodeSetConnection
        # args: GraphQL Query
        # iterable: QuerySet

        connection = super().resolve_connection(connection, args, iterable, *nargs, **kwargs)

        start_offset = utils.resolve_start_offset(0, args.get("after"))
        connection.page_info.has_previous_page = start_offset > 0

        return connection

    obvious_filters = [
        filters.IntFilter,
    ]

    @property
    def filtering_args(self):
        return utils.get_filtering_args_from_filterset(
            self.filterset_class, self.node_type, obvious_filters=self.obvious_filters
        )

    @classmethod
    def resolve_queryset(cls, connection, iterable, info, args, filtering_args, filterset_class):
        qs = super().resolve_queryset(connection, iterable, info, args, filtering_args, filterset_class)

        # Apply distinct() only when needed (M2M, reverse FK, or explicit distinct=True)
        if _needs_distinct(qs, args, filterset_class):
            return qs.distinct()

        return qs
