"""Tests for the model metadata `BaseFilter` copies onto its ``exact`` filters.

No database is needed: filtersets are inspected as declarations. ``base_filters`` is
built by django-filter's metaclass at class-creation time, which is exactly why the
lazy-translation test below matters.
"""

import django_filters
from django.db import models
from django.utils.functional import Promise

from apibase.filters import BaseFilter, IntFilter, clone_filter_fields
from tests.models import Described


class _DescribedFilter(BaseFilter):
    name__contains = django_filters.CharFilter(field_name="name", lookup_expr="contains")

    class Meta:
        model = Described
        fields = ["name", "status", "lazy_named", "plain", "two_words"]


def test_exact_filter_takes_label_and_help_text_from_the_model_field():
    flt = _DescribedFilter.base_filters["name"]

    assert flt.label == "名前"
    assert flt.extra["help_text"] == "完全一致で絞り込む"


def test_auto_derived_verbose_name_is_left_to_django_filter():
    # Django derives a verbose_name ("plain") for a field that declares none. Adopting
    # it would replace django-filter's own "Plain" with a lowercased version, so a
    # field with nothing to say must keep label=None.
    flt = _DescribedFilter.base_filters["plain"]

    assert flt.label is None
    assert "help_text" not in flt.extra


def test_a_multiword_field_name_does_not_look_like_an_explicit_verbose_name():
    # The derived form replaces underscores with spaces, so "two words" must still be
    # recognised as derived rather than adopted as a label.
    flt = _DescribedFilter.base_filters["two_words"]

    assert flt.label is None


def test_metadata_survives_the_int_choices_narrowing_to_intfilter():
    # An IntegerField with choices is narrowed from ChoiceFilter to IntFilter, and
    # that branch resets ``param``. The metadata must be applied after the reset.
    flt = _DescribedFilter.base_filters["status"]

    assert isinstance(flt, IntFilter)
    assert flt.label == "状態"
    assert flt.extra["help_text"] == "状態コード"


def test_lazy_translations_are_not_evaluated_at_class_creation():
    # str() here would freeze the translation to whichever locale happened to be
    # active when the module was imported.
    flt = _DescribedFilter.base_filters["lazy_named"]

    assert isinstance(flt.label, Promise)
    assert isinstance(flt.extra["help_text"], Promise)


def test_non_exact_lookups_are_left_alone():
    flt = _DescribedFilter.declared_filters["name__contains"]

    assert flt.label is None
    assert "help_text" not in flt.extra


def test_filter_overrides_win_over_the_model_field_metadata():
    class _OverriddenFilter(BaseFilter):
        class Meta:
            model = Described
            fields = ["name"]
            filter_overrides = {
                models.CharField: {
                    "filter_class": django_filters.CharFilter,
                    "extra": lambda field: {"label": "明示ラベル", "help_text": "明示ヘルプ"},
                }
            }

    flt = _OverriddenFilter.base_filters["name"]

    assert flt.label == "明示ラベル"
    assert flt.extra["help_text"] == "明示ヘルプ"


def test_clone_filter_fields_carries_help_text_along_with_label():
    # ``label`` is a named argument on Filter, ``help_text`` lives in ``extra``;
    # cloning only the former would leave related filtersets half-described.
    cloned = clone_filter_fields(_DescribedFilter, "described")

    assert cloned["described__name"].label == "名前"
    assert cloned["described__name"].extra["help_text"] == "完全一致で絞り込む"


def test_clone_filter_fields_leaves_help_text_unset_when_the_source_has_none():
    cloned = clone_filter_fields(_DescribedFilter, "described")

    assert "help_text" not in cloned["described__plain"].extra
