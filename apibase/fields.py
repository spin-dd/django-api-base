import calendar
from datetime import date
from typing import Any, Callable

from django import forms
from django.core.exceptions import ValidationError
from django.forms.widgets import SelectMultiple
from django_filters.fields import RangeField
from django_filters.widgets import SuffixedMultiWidget


class ListFieldMixin:
    # サブクラスが int などに差し替えるので、str に推論させない。
    converter: Callable[[Any], Any] = str

    def to_python_value(self, value):
        if not value:
            return []
        elif not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages["invalid_list"], code="invalid_list")
        return [self.converter(val) for val in value]


class ListCharField(forms.CharField, ListFieldMixin):
    widget = SelectMultiple
    converter = str

    def to_python(self, value):
        return self.to_python_value(value)


class ListIntegerField(forms.IntegerField, ListFieldMixin):
    widget = SelectMultiple
    converter = int

    def to_python(self, value):
        return self.to_python_value(value)


class CharRangeField(RangeField):
    def __init__(self, fields=None, *args, **kwargs):
        if fields is None:
            fields = (forms.CharField(), forms.CharField())
        super().__init__(fields, *args, **kwargs)


class CharRangeWidget(SuffixedMultiWidget):
    suffixes = ["after", "before"]

    def __init__(self, attrs=None):
        widgets = (forms.TextInput, forms.TextInput)
        super().__init__(widgets, attrs)

    def value_from_datadict(self, data, files, name):
        res = super().value_from_datadict(data, files, name)
        return [isinstance(i, list) and i[0] or i for i in res]


class MonthRangeField(CharRangeField):
    widget = CharRangeWidget

    def to_date(self, value, last=False):
        if value:
            ret = date(int(str(value)[:4]), int(str(value)[4:]), 1)
            if last:
                _, day = calendar.monthrange(ret.year, ret.month)
                return ret.replace(day=day)
            return ret

    def compress(self, data_list):
        data = data_list and [
            self.to_date(data_list[0]),
            self.to_date(data_list[1], last=True),
        ]
        if data:
            return slice(*data)
        return None
