"""
https://django-filter.readthedocs.io/en/stable/
"""
import operator
import re
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
            vals = set(
                [
                    jaconv.zen2han(val, ascii=True, kana=True, digit=True),
                    jaconv.han2zen(val, ascii=True, kana=True, digit=True),
                ]
            )
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
                # print(field)
                filter_class = IntFilter
                param = {}

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


def clone_filter_fields(filter_class, prefix, distinct=None, fields=None, exclude=None):
    def _item(key, instance, distinct=None):
        # TOOD: method
        params = {}
        if hasattr(instance, "queryset"):
            params["queryset"] = instance.queryset
        elif hasattr(instance.field, "choices"):
            params["choices"] = instance.field.choices

        if isinstance(instance, WordFilter):
            params["lookups"] = [f"{prefix}__{i}" for i in instance.lookups]
            params["delimiters"] = instance.delimiters

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

    return {
        **dict(_item(key, instance, distinct=distinct) for key, instance in filter_class.declared_filters.items()),
        **dict(_item(key, instance, distinct=distinct) for key, instance in filter_class.base_filters.items()),
    }


def make_related_filterset(type_name, distinct=True, base_filters=None, **related_filters):
    base_filters = base_filters or (BaseFilter,)
    fields = reduce(
        lambda a, b: {**a, **b},
        [
            clone_filter_fields(filter_class, prefix, distinct=distinct)
            for prefix, filter_class in related_filters.items()
        ],
    )
    return type(type_name, base_filters, fields)


class RelatedFilterSetMixin:
    @classmethod
    def create_related_filterset(cls, related_name):
        fields = clone_filter_fields(cls, related_name)
        return type(f"RelatedFilter_{related_name}", (django_filters.FilterSet,), fields)


class CharRangeFilter(django_filters.RangeFilter):
    field_class = CharRangeField

    def filter(self, qs, value):
        if not value or (not value.start and not value.stop):
            return qs

        q0 = value.start and Q(**{f"{self.field_name}__gte": value.start}) or Q()
        q1 = value.stop and Q(**{f"{self.field_name}__lte": value.stop}) or Q()

        return self.get_method(self.distinct and qs.distinct() or qs)(q0 & q1)
