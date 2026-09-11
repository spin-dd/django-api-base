"""
https://django-filter.readthedocs.io/en/stable/
"""

import operator
import re
from collections.abc import Mapping
from functools import reduce

import django_filters
import jaconv
from django import forms
from django.db.models import IntegerField, Q

from .fields import CharRangeField, ListCharField, ListIntegerField, MonthRangeField


class IntFilter(django_filters.NumberFilter):
    field_class = forms.IntegerField


SPACES = r"[\s\u3000,]+"


class WordFilter(django_filters.CharFilter):
    def __init__(self, *args, lookups=None, delimiters=None, **kwargs):
        self.lookups = lookups or []
        self.delimiters = delimiters or SPACES
        kwargs["lookup_expr"] = kwargs.get("lookup_expr", "contains")
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value in django_filters.constants.EMPTY_VALUES:
            return qs

        def _q(lookup, val):
            key = f"{lookup}__{self.lookup_expr}"
            vals = {
                jaconv.zen2han(val, ascii=True, kana=True, digit=True),
                jaconv.han2zen(val, ascii=True, kana=True, digit=True),
            }
            return reduce(operator.or_, (Q(**{key: v}) for v in vals))

        vals = re.split(self.delimiters, value)
        query = [reduce(operator.or_, [_q(i, v) for i in self.lookups]) for v in vals if v]

        qs = qs.filter(*query)
        if self.distinct:
            qs = qs.distinct()
        return qs


class ListCharInFilter(django_filters.CharFilter):
    field_class = ListCharField

    def get_filter_predicate(self, v):
        return {f"{self.field_name}__in": v}

    def filter(self, qs, values):
        if not values:
            return qs

        predicate = self.get_filter_predicate(values)
        qs = self.get_method(qs)(**predicate)
        return qs.distinct() if self.distinct else qs


class ListIntegerInFilter(ListCharInFilter):
    field_class = ListIntegerField


def _explicit_verbose_name(field):
    """Return ``field.verbose_name``, but only when the model actually declared one.

    Django fills ``verbose_name`` in from the attribute name for any field that does
    not declare one (``Field.set_attributes_from_name``), so a bare field hands us
    "created at" -- and adopting that would *replace* django-filter's own "Created at"
    with a worse label on every field in the project. Comparing against the derived
    form is how the two are told apart; a field that explicitly declares exactly the
    derived string is indistinguishable, and losing that case costs nothing.
    """
    verbose_name = getattr(field, "verbose_name", None)
    name = getattr(field, "name", None)
    if not verbose_name or not name:
        return None
    return None if verbose_name == name.replace("_", " ") else verbose_name


class BaseFilter(django_filters.FilterSet):
    pk = django_filters.NumberFilter(field_name="id")

    id__includes = ListIntegerInFilter(label="ID(PK)", field_name="id", help_text="includes id set in csv")

    id__excludes = ListIntegerInFilter(
        label="ID(PK)", field_name="id", exclude=True, help_text="exclude id set in csv"
    )

    @classmethod
    def filter_for_lookup(cls, field, lookup_type):
        filter_class, param = super().filter_for_lookup(field, lookup_type)

        if lookup_type == "exact" and filter_class == django_filters.ChoiceFilter:
            if isinstance(field, IntegerField):
                filter_class = IntFilter
                param = {}

        if filter_class is not None and lookup_type == "exact":
            # モデルフィールドの説明を exact フィルタのラベル / ヘルプに引き継ぐ。
            # setdefault なのは Meta.filter_overrides の extra が明示した値を勝たせるため。
            # str() は掛けない。verbose_name / help_text が gettext_lazy のとき、
            # FilterSet は import 時にメタクラスで組み立てられるので、ここで評価すると
            # そのときのロケールに翻訳が固定される。lazy のまま渡せば描画時に評価される。
            verbose_name = _explicit_verbose_name(field)
            if verbose_name:
                param.setdefault("label", verbose_name)

            if getattr(field, "help_text", None):
                param.setdefault("help_text", field.help_text)

        return filter_class, param

    def filter_int(self, queryset, name, value):
        q = {name: int(round(value))}
        return queryset.filter(**q)

    id__in_csv = django_filters.BaseInFilter(
        label="ID",
        field_name="id",
    )

    id__not_in_csv = django_filters.BaseInFilter(
        label="ID",
        field_name="id",
        exclude=True,
    )


class AllValuesMultipleFilter(django_filters.AllValuesMultipleFilter):
    # field_class: django_filters.fields.MultipleChoiceField

    @property
    def field(self):
        # not cache as '_field' to work with `choices`
        if hasattr(self, "model"):
            qs = self.model._default_manager.distinct()
            qs = qs.order_by(self.field_name).values_list(self.field_name, flat=True)
            self.extra["choices"] = [(o, o) for o in qs]
        field_kwargs = self.extra.copy()
        return self.field_class(label=self.label, **field_kwargs)

    def get_filter_predicate(self, v):
        # 'field_name' MUST BE endswith "__in"
        return {f"{self.field_name}__in": v}


class MonthFromToRangeFilter(django_filters.RangeFilter):
    field_class = MonthRangeField


CLONE_METHOD_POLICIES = ("keep", "drop", "error")


def validate_method_filters(filter_class):
    """Return ``(filter_key, method_name)`` for each string ``method`` the class cannot resolve.

    django-filter looks a string ``method`` up on the running filterset, so a composed
    class (see `clone_filter_fields`) imports cleanly and then raises on the first
    request that uses the parameter. Assert this is empty over your own filtersets to
    turn that into a test failure.

    Only the name is checked, on the class. A name that resolves to something the
    filterset already owns (``filter_queryset``, say) passes here and still fails at
    query time on the ``(queryset, name, value)`` signature, and a method installed on
    the instance at ``__init__`` time is reported even though it would resolve.
    """
    filters = {
        **getattr(filter_class, "declared_filters", {}),
        **getattr(filter_class, "base_filters", {}),
    }
    return [
        (key, instance.method)
        for key, instance in filters.items()
        if isinstance(getattr(instance, "method", None), str)
        and not callable(getattr(filter_class, instance.method, None))
    ]


def _select_filter_keys(source, filter_class, fields, exclude):
    if fields is not None and exclude is not None:
        raise TypeError("clone_filter_fields() accepts 'fields' or 'exclude', not both.")

    for label, names in (("fields", fields), ("exclude", exclude)):
        if names is None:
            continue
        unknown = sorted(set(names) - set(source))
        if unknown:
            raise ValueError(
                f"clone_filter_fields() got unknown {label} name(s) {unknown} "
                f"for {filter_class.__name__}. Names are the source filter keys, not the prefixed ones."
            )

    if fields is not None:
        wanted = set(fields)
        return [key for key in source if key in wanted]
    if exclude is not None:
        unwanted = set(exclude)
        return [key for key in source if key not in unwanted]
    return list(source)


def _apply_method_policy(source, keys, filter_class, methods):
    if methods not in CLONE_METHOD_POLICIES:
        raise ValueError(f"clone_filter_fields() got methods={methods!r}; expected one of {CLONE_METHOD_POLICIES}.")
    if methods == "keep":
        return keys

    named = {key for key in keys if isinstance(getattr(source[key], "method", None), str)}
    if not named:
        return keys
    if methods == "drop":
        return [key for key in keys if key not in named]

    raise ValueError(
        f"clone_filter_fields() will not clone the string-method filter(s) {sorted(named)} "
        f"of {filter_class.__name__} under methods='error': the method is looked up on the "
        "filterset that ends up owning the clone. Define the method there and use "
        "methods='keep', or leave them out with 'exclude'."
    )


def clone_filter_fields(filter_class, prefix, distinct=None, fields=None, exclude=None, methods="keep"):
    """Clone ``filter_class``'s filters under ``prefix`` (``prefix__<key>``).

    ``fields`` / ``exclude`` name **source** filter keys (before prefixing) and are
    mutually exclusive; an unknown name raises rather than silently widening the
    cloned set.

    ``methods`` decides what happens to filters declared with a *string* ``method``
    (``keep`` clones them, ``drop`` leaves them out, ``error`` refuses). Such a method
    is looked up on whichever filterset ends up owning the clone, and django-filter
    resolves it lazily — a name that does not resolve there imports cleanly and raises
    at query time. Beyond the name, the method carries the source filterset's queryset
    assumptions (its model, its relation depth) into the clone, so a resolvable name is
    not by itself proof the clone means the same thing. Assert `validate_method_filters`
    over the composed class.
    """

    def _item(key, instance, distinct=None):
        params = {}
        if hasattr(instance, "queryset"):
            params["queryset"] = instance.queryset
        elif hasattr(instance.field, "choices"):
            params["choices"] = instance.field.choices

        if isinstance(instance, WordFilter):
            params["lookups"] = [f"{prefix}__{i}" for i in instance.lookups]
            params["delimiters"] = instance.delimiters

        # help_text は label と違って named argument ではなく ``extra`` に入るので、
        # 明示的に拾わないと複製で落ちる。label だけ残って説明が消えるのを避ける。
        if "help_text" in instance.extra:
            params["help_text"] = instance.extra["help_text"]

        distinct = distinct if distinct is not None else instance.distinct
        return (
            f"{prefix}__{key}",
            instance.__class__(
                label=instance.label,
                field_name=f"{prefix}__{instance.field_name}",
                distinct=distinct,
                exclude=instance.exclude,
                lookup_expr=instance.lookup_expr,
                method=instance.method,
                **params,
            ),
        )

    source = {**filter_class.declared_filters, **filter_class.base_filters}
    keys = _select_filter_keys(source, filter_class, fields, exclude)
    keep = set(_apply_method_policy(source, keys, filter_class, methods))

    # Declared first, then base, so that both the key order and "base wins" match
    # what callers already have: the order decides the order filters are applied in.
    return {
        **dict(
            _item(key, instance, distinct=distinct)
            for key, instance in filter_class.declared_filters.items()
            if key in keep
        ),
        **dict(
            _item(key, instance, distinct=distinct)
            for key, instance in filter_class.base_filters.items()
            if key in keep
        ),
    }


CLONE_PREFIX_OPTIONS = ("fields", "exclude", "methods", "distinct")


def _is_filterset(value):
    """True for a filterset class, or one that walks like one.

    `clone_filter_fields` only reads ``declared_filters`` / ``base_filters`` off the
    class, so a duck-typed one has always worked and stays accepted. Checking for them
    is what turns the likely slip — passing a *model* where its filterset belongs —
    into a `TypeError` here instead of an `AttributeError` from inside the clone.
    """
    if not isinstance(value, type):
        return False
    if issubclass(value, django_filters.FilterSet):
        return True
    return hasattr(value, "declared_filters") and hasattr(value, "base_filters")


def _is_relation(value):
    """True for either accepted relation value: a filterset class, or ``(class, options)``."""
    if _is_filterset(value):
        return True
    return isinstance(value, (tuple, list)) and len(value) == 2 and _is_filterset(value[0])


def _relation_clone_options(prefix, value, distinct, methods):
    """Resolve one ``prefix=<relation>`` entry into ``(filter_class, clone_kwargs)``."""
    defaults = {"distinct": distinct, "methods": methods}
    if _is_filterset(value):
        return value, defaults

    if not _is_relation(value):
        raise TypeError(
            f"make_related_filterset() got {prefix}={value!r}; expected a filterset class "
            "or a (filterset class, options) pair."
        )

    filter_class, overrides = value
    if not isinstance(overrides, Mapping):
        raise TypeError(
            f"make_related_filterset() got {prefix}=({filter_class.__name__}, {overrides!r}); "
            "the second item holds the per-prefix options and has to be a mapping."
        )

    unknown = sorted(set(overrides) - set(CLONE_PREFIX_OPTIONS))
    if unknown:
        raise TypeError(
            f"make_related_filterset() got unknown option(s) {unknown} for {prefix}; "
            f"expected any of {list(CLONE_PREFIX_OPTIONS)}."
        )

    # The per-prefix options win: the call-wide ``distinct`` / ``methods`` are the
    # defaults for prefixes that do not say otherwise.
    options = {**defaults, **overrides}

    # `clone_filter_fields` would reject an unusable policy too, but without saying
    # which prefix carried it — and a call has one policy per prefix now.
    if options["methods"] not in CLONE_METHOD_POLICIES:
        raise ValueError(
            f"make_related_filterset() got methods={options['methods']!r} for {prefix}; "
            f"expected one of {CLONE_METHOD_POLICIES}."
        )
    return filter_class, options


def make_related_filterset(type_name, distinct=True, base_filters=None, **related_filters):
    """Build a filterset from ``prefix=<relation>`` pairs, one clone per prefix.

    A relation is either a filterset class, or a ``(filterset class, options)`` pair
    whose options are passed to `clone_filter_fields` for that prefix alone
    (``fields`` / ``exclude`` / ``methods`` / ``distinct``)::

        make_related_filterset(
            "Related",
            customer=(CustomerFilter, {"fields": ["code", "name__contains"]}),
            order=(OrderFilter, {"exclude": ["heavy_method_filter"]}),
            shipment=ShipmentFilter,
        )

    ``fields`` / ``exclude`` are per-prefix only — they name *source* filter keys, which
    differ from one prefix to the next. ``methods=<policy>`` remains available as a
    keyword and sets the policy for every prefix that does not override it.

    ``methods`` is also a plausible relation name, so a relation passed there stays a
    prefix — at the cost of not being able to set the call-wide policy in the same call.
    It is read out of the keyword arguments rather than declared as a parameter so that
    the remaining prefixes keep the order they were written in: that order is the order
    the cloned filters are applied in. ``type_name`` / ``distinct`` / ``base_filters``
    are reserved outright; a relation named after one of those has to go through
    `clone_filter_fields` directly.
    """
    methods = "keep"
    if "methods" in related_filters:
        policy = related_filters["methods"]
        if isinstance(policy, str):
            methods = related_filters.pop("methods")
        elif not _is_relation(policy):
            raise TypeError(
                f"make_related_filterset() got methods={policy!r}; expected one of "
                f"{CLONE_METHOD_POLICIES} (the clone policy), or a filterset class or "
                "(filterset class, options) pair (a relation prefix)."
            )

    # Checked here as well as in the clone, so that an unusable policy is reported even
    # when popping it left no prefix for `clone_filter_fields` to be reached through.
    if methods not in CLONE_METHOD_POLICIES:
        raise ValueError(f"make_related_filterset() got methods={methods!r}; expected one of {CLONE_METHOD_POLICIES}.")

    base_filters = base_filters or (BaseFilter,)
    relations = [
        (prefix, _relation_clone_options(prefix, value, distinct, methods))
        for prefix, value in related_filters.items()
    ]
    if not relations:
        # reduce() over nothing raises "reduce() of empty iterable with no initial
        # value", which says nothing about the call that caused it.
        raise TypeError(f"make_related_filterset({type_name!r}) needs at least one prefix=<relation> keyword.")

    fields = reduce(
        lambda a, b: {**a, **b},
        [clone_filter_fields(filter_class, prefix, **options) for prefix, (filter_class, options) in relations],
    )
    return type(type_name, base_filters, fields)


class RelatedFilterSetMixin:
    @classmethod
    def create_related_filterset(cls, related_name, fields=None, exclude=None, methods="keep"):
        """Clone this filterset's filters under ``related_name`` onto a bare FilterSet.

        The generated class carries no methods of its own, so a *string* ``method``
        cloned into it can never resolve: under the default ``methods='keep'`` it
        raises `AssertionError` on the first request that uses the parameter. That is
        the existing behaviour and it at least fails loudly, but pass ``'drop'`` to
        leave those filters out, or ``'error'`` to be told at import time.
        """
        cloned = clone_filter_fields(cls, related_name, fields=fields, exclude=exclude, methods=methods)
        return type(f"RelatedFilter_{related_name}", (django_filters.FilterSet,), cloned)


class CharRangeFilter(django_filters.RangeFilter):
    field_class = CharRangeField

    def filter(self, qs, value):
        if not value or (not value.start and not value.stop):
            return qs

        q0 = value.start and Q(**{f"{self.field_name}__gte": value.start}) or Q()
        q1 = value.stop and Q(**{f"{self.field_name}__lte": value.stop}) or Q()

        return self.get_method(self.distinct and qs.distinct() or qs)(q0 & q1)
