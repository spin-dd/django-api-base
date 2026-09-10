"""Tests for `apibase.filters.clone_filter_fields` scoping and string-method handling.

No database is needed: the filters are inspected as declarations, and the one test
that applies a filter does so against a lazy queryset, so the resolution assert fires
before any SQL.
"""

import django_filters
import pytest

from apibase.filters import (
    BaseFilter,
    RelatedFilterSetMixin,
    clone_filter_fields,
    make_related_filterset,
    validate_method_filters,
)
from tests.models import Child, Parent


class _CloneSourceFilter(BaseFilter):
    """Source filterset, cloned onto ``Child`` under the ``parent`` prefix."""

    name__contains = django_filters.CharFilter(field_name="name", lookup_expr="contains")
    named_like = django_filters.CharFilter(method="filter_named_like")

    class Meta:
        model = Parent
        fields = []

    def filter_named_like(self, queryset, name, value):
        return queryset.filter(**{f"{name}__contains": value})


def _child_filterset(fields):
    meta = type("Meta", (), {"model": Child, "fields": []})
    return type("_ClonedChildFilter", (django_filters.FilterSet,), dict(fields, Meta=meta))


def test_clone_filter_fields_clones_every_filter_by_default():
    cloned = clone_filter_fields(_CloneSourceFilter, "parent")

    assert "parent__name__contains" in cloned
    assert "parent__pk" in cloned
    assert cloned["parent__name__contains"].field_name == "parent__name"


def test_clone_filter_fields_keeps_declared_filters_before_generated_ones():
    # The clone's order is the order the filters are applied in, so it follows the
    # source's "declared, then generated" order rather than ``base_filters`` order
    # (django-filter puts Meta-generated filters first there).
    class _OrderProbeFilter(BaseFilter):
        zzz__contains = django_filters.CharFilter(field_name="name", lookup_expr="contains")

        class Meta:
            model = Parent
            fields = ["name"]

    cloned = list(clone_filter_fields(_OrderProbeFilter, "parent"))

    assert cloned.index("parent__zzz__contains") < cloned.index("parent__name")


def test_clone_filter_fields_fields_limits_the_cloned_set():
    cloned = clone_filter_fields(_CloneSourceFilter, "parent", fields=["name__contains"])

    assert set(cloned) == {"parent__name__contains"}


def test_clone_filter_fields_exclude_drops_named_filters():
    cloned = clone_filter_fields(_CloneSourceFilter, "parent", exclude=["name__contains"])

    assert "parent__name__contains" not in cloned
    assert "parent__pk" in cloned


def test_clone_filter_fields_rejects_fields_and_exclude_together():
    with pytest.raises(TypeError):
        clone_filter_fields(_CloneSourceFilter, "parent", fields=["name__contains"], exclude=["pk"])


@pytest.mark.parametrize("kwarg", ["fields", "exclude"])
def test_clone_filter_fields_rejects_unknown_names(kwarg):
    # A typo must not silently widen (fields) or silently no-op (exclude) the clone.
    with pytest.raises(ValueError, match="no_such_filter"):
        clone_filter_fields(_CloneSourceFilter, "parent", **{kwarg: ["no_such_filter"]})


def test_cloned_string_method_stays_unresolved_until_query_time():
    # The trap this helper sets: declaring the clone is silent, and the failure
    # lands on whoever first uses the query parameter.
    cloned = _child_filterset(clone_filter_fields(_CloneSourceFilter, "parent"))

    with pytest.raises(AssertionError, match="filter_named_like"):
        _ = cloned({"parent__named_like": "x"}, queryset=Child.objects.all()).qs


def test_validate_method_filters_reports_unresolvable_methods():
    cloned = _child_filterset(clone_filter_fields(_CloneSourceFilter, "parent"))

    assert validate_method_filters(cloned) == [("parent__named_like", "filter_named_like")]


def test_validate_method_filters_passes_when_the_method_resolves():
    assert validate_method_filters(_CloneSourceFilter) == []


def test_clone_filter_fields_methods_drop_skips_string_method_filters():
    cloned = clone_filter_fields(_CloneSourceFilter, "parent", methods="drop")

    assert "parent__named_like" not in cloned
    assert "parent__name__contains" in cloned


def test_clone_filter_fields_methods_error_names_the_offending_filters():
    with pytest.raises(ValueError, match="named_like"):
        clone_filter_fields(_CloneSourceFilter, "parent", methods="error")


def test_clone_filter_fields_rejects_unknown_method_policy():
    with pytest.raises(ValueError, match="methods"):
        clone_filter_fields(_CloneSourceFilter, "parent", methods="maybe")


def test_clone_filter_fields_keeps_callable_methods_under_every_policy():
    # A callable ``method`` needs no lookup on the parent, so it is not what the
    # policy is about.
    class _CallableMethodFilter(BaseFilter):
        named_like = django_filters.CharFilter(method=lambda qs, name, value: qs)

        class Meta:
            model = Parent
            fields = []

    cloned = clone_filter_fields(_CallableMethodFilter, "parent", methods="drop")

    assert "parent__named_like" in cloned


def test_make_related_filterset_forwards_the_method_policy():
    related = make_related_filterset("_Related", methods="drop", parent=_CloneSourceFilter)

    assert "parent__named_like" not in related.base_filters
    assert "parent__name__contains" in related.base_filters


def test_make_related_filterset_still_accepts_a_relation_named_methods():
    # ``methods`` is a plausible relation name (payment methods, delivery methods),
    # and it was a usable prefix before the policy kwarg existed.
    related = make_related_filterset("_Related", methods=_CloneSourceFilter)

    assert "methods__name__contains" in related.base_filters
    assert "methods__named_like" in related.base_filters


def test_make_related_filterset_keeps_the_methods_prefix_alongside_other_relations():
    related = make_related_filterset("_Related", methods=_CloneSourceFilter, other=_CloneSourceFilter)

    assert "methods__name__contains" in related.base_filters
    assert "other__name__contains" in related.base_filters


def test_make_related_filterset_keeps_a_methods_prefix_in_the_order_it_was_written():
    # Prefix order is the order the cloned filters are applied in, so pulling the
    # policy out of the keywords must not move a prefix that happens to be named
    # after it to the end.
    keys = list(make_related_filterset("_Related", methods=_CloneSourceFilter, other=_CloneSourceFilter).base_filters)

    assert keys.index("methods__name__contains") < keys.index("other__name__contains")


def test_make_related_filterset_rejects_a_methods_value_that_is_neither_policy_nor_filterset():
    with pytest.raises(TypeError, match="methods"):
        make_related_filterset("_Related", parent=_CloneSourceFilter, methods=None)


@pytest.mark.parametrize(
    "related",
    [
        pytest.param({"parent": _CloneSourceFilter}, id="with-another-prefix"),
        # Popping the policy leaves no prefix at all, so nothing reaches the clone:
        # the policy still has to be reported rather than an internal reduce() error.
        pytest.param({}, id="as-the-only-keyword"),
    ],
)
def test_make_related_filterset_rejects_an_unknown_policy(related):
    with pytest.raises(ValueError, match="maybe"):
        make_related_filterset("_Related", methods="maybe", **related)


def test_create_related_filterset_forwards_scoping_and_method_policy():
    class _MixedSourceFilter(RelatedFilterSetMixin, _CloneSourceFilter):
        class Meta:
            model = Parent
            fields = []

    related = _MixedSourceFilter.create_related_filterset("parent", methods="drop")

    assert "parent__named_like" not in related.base_filters
    assert validate_method_filters(related) == []
