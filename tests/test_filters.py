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
        fields: list[str] = []

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


# --- per-prefix options: ``prefix=(filter_class, options)`` ---------------------------


def test_make_related_filterset_scopes_fields_per_prefix():
    related = make_related_filterset(
        "_Related",
        parent=(_CloneSourceFilter, {"fields": ["name__contains"]}),
    )

    assert "parent__name__contains" in related.base_filters
    assert "parent__named_like" not in related.base_filters


def test_make_related_filterset_excludes_per_prefix():
    related = make_related_filterset(
        "_Related",
        parent=(_CloneSourceFilter, {"exclude": ["named_like"]}),
    )

    assert "parent__name__contains" in related.base_filters
    assert "parent__named_like" not in related.base_filters


def test_make_related_filterset_scopes_each_prefix_independently():
    # The whole point of moving the options next to the prefix: ``fields`` names source
    # keys, so one list cannot serve two relations.
    related = make_related_filterset(
        "_Related",
        kept=(_CloneSourceFilter, {"fields": ["named_like"]}),
        trimmed=(_CloneSourceFilter, {"exclude": ["named_like"]}),
    )

    assert "kept__named_like" in related.base_filters
    assert "kept__name__contains" not in related.base_filters
    assert "trimmed__name__contains" in related.base_filters
    assert "trimmed__named_like" not in related.base_filters


def test_make_related_filterset_still_accepts_a_bare_class_alongside_a_pair():
    related = make_related_filterset(
        "_Related",
        scoped=(_CloneSourceFilter, {"fields": ["name__contains"]}),
        whole=_CloneSourceFilter,
    )

    assert "scoped__named_like" not in related.base_filters
    assert "whole__named_like" in related.base_filters
    assert "whole__name__contains" in related.base_filters


def test_make_related_filterset_keeps_prefix_order_with_pairs():
    # Key order is the order the cloned filters are applied in. Resolving a pair must
    # not move that prefix relative to the ones written around it.
    keys = list(
        make_related_filterset(
            "_Related",
            first=_CloneSourceFilter,
            second=(_CloneSourceFilter, {"exclude": ["named_like"]}),
            third=_CloneSourceFilter,
        ).base_filters
    )

    assert keys.index("first__name__contains") < keys.index("second__name__contains")
    assert keys.index("second__name__contains") < keys.index("third__name__contains")


def test_make_related_filterset_keeps_the_source_key_order_within_a_scoped_prefix():
    # ``fields`` is a filter, not a reordering: the surviving keys keep the order
    # `clone_filter_fields` would have given them, not the order they were listed in.
    scoped = list(
        make_related_filterset(
            "_Related",
            parent=(_CloneSourceFilter, {"fields": ["named_like", "name__contains"]}),
        ).base_filters
    )
    whole = list(make_related_filterset("_Related", parent=_CloneSourceFilter).base_filters)

    assert scoped == [key for key in whole if key in scoped]


def test_make_related_filterset_per_prefix_methods_overrides_the_call_wide_policy():
    related = make_related_filterset(
        "_Related",
        methods="drop",
        dropped=_CloneSourceFilter,
        kept=(_CloneSourceFilter, {"methods": "keep"}),
    )

    assert "dropped__named_like" not in related.base_filters
    assert "kept__named_like" in related.base_filters


def test_make_related_filterset_per_prefix_distinct_overrides_the_call_wide_default():
    related = make_related_filterset(
        "_Related",
        parent=_CloneSourceFilter,
        other=(_CloneSourceFilter, {"distinct": False}),
    )

    assert related.base_filters["parent__name__contains"].distinct is True
    assert related.base_filters["other__name__contains"].distinct is False


def test_make_related_filterset_accepts_a_pair_under_a_relation_named_methods():
    # ``methods`` stays usable as a prefix in the pair form too, not just as a bare class.
    related = make_related_filterset(
        "_Related",
        methods=(_CloneSourceFilter, {"exclude": ["named_like"]}),
    )

    assert "methods__name__contains" in related.base_filters
    assert "methods__named_like" not in related.base_filters


def test_make_related_filterset_rejects_an_unknown_per_prefix_option():
    with pytest.raises(TypeError, match="unknown option"):
        make_related_filterset("_Related", parent=(_CloneSourceFilter, {"field": ["name__contains"]}))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param((_CloneSourceFilter,), id="one-item"),
        pytest.param((_CloneSourceFilter, {}, "extra"), id="three-items"),
        pytest.param(({"fields": []}, _CloneSourceFilter), id="reversed"),
        pytest.param("not-a-filterset", id="a-string"),
    ],
)
def test_make_related_filterset_rejects_a_malformed_relation(value):
    with pytest.raises(TypeError, match="expected a filterset class"):
        make_related_filterset("_Related", parent=value)


def test_make_related_filterset_rejects_non_mapping_per_prefix_options():
    with pytest.raises(TypeError, match="has to be a mapping"):
        make_related_filterset("_Related", parent=(_CloneSourceFilter, ["name__contains"]))


def test_make_related_filterset_still_rejects_fields_and_exclude_together():
    # The clone owns that rule; the pair form must not swallow it.
    with pytest.raises(TypeError, match="not both"):
        make_related_filterset(
            "_Related",
            parent=(_CloneSourceFilter, {"fields": ["named_like"], "exclude": ["name__contains"]}),
        )


def test_make_related_filterset_still_rejects_an_unknown_field_name():
    with pytest.raises(ValueError, match="nonexistent"):
        make_related_filterset("_Related", parent=(_CloneSourceFilter, {"fields": ["nonexistent"]}))


def test_make_related_filterset_rejects_a_class_that_is_not_a_filterset():
    # The likely slip is passing the model where its filterset belongs; without a
    # check that surfaces as AttributeError from inside the clone.
    with pytest.raises(TypeError, match="expected a filterset class"):
        make_related_filterset("_Related", parent=Parent)


def test_make_related_filterset_accepts_a_duck_typed_filterset():
    # `clone_filter_fields` only reads these two attributes, so a class that has them
    # has always worked and must keep working.
    duck = type("_Duck", (), {"declared_filters": {}, "base_filters": {}})

    assert make_related_filterset("_Related", parent=duck).base_filters is not None


def test_make_related_filterset_names_the_prefix_in_a_per_prefix_policy_error():
    with pytest.raises(ValueError, match="for parent"):
        make_related_filterset(
            "_Related",
            other=_CloneSourceFilter,
            parent=(_CloneSourceFilter, {"methods": "maybe"}),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="no-keywords"),
        # The policy is not a relation, so popping it can leave nothing behind.
        pytest.param({"methods": "drop"}, id="only-the-policy"),
    ],
)
def test_make_related_filterset_rejects_a_call_with_no_relation(kwargs):
    with pytest.raises(TypeError, match="at least one prefix"):
        make_related_filterset("_Related", **kwargs)
