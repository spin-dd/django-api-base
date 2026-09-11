from django.db import models
from django.utils.translation import gettext_lazy


class Parent(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"


class Child(models.Model):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"


class Described(models.Model):
    """Fields carrying explicit metadata, for the exact-filter label/help_text tests."""

    STATUS_CHOICES = [(1, "draft"), (2, "published")]

    name = models.CharField("名前", max_length=100, help_text="完全一致で絞り込む")
    status = models.IntegerField("状態", choices=STATUS_CHOICES, help_text="状態コード")
    lazy_named = models.CharField(gettext_lazy("lazy label"), max_length=100, help_text=gettext_lazy("lazy help"))
    plain = models.CharField(max_length=100)
    two_words = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"
