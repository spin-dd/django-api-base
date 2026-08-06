from django.db import models


class Parent(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"


class Child(models.Model):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "tests"
