from django.db.migrations.serializer import serializer_factory
from rest_framework import serializers


class ModelFieldSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        field = dict(zip(("name", "type", "args", "kwargs"), instance.deconstruct()))
        field["args"] = [serializer_factory(i).serialize()[0] for i in field["args"]]
        field["kwargs"] = dict((k, serializer_factory(v).serialize()[0]) for (k, v) in field["kwargs"].items())

        model = dict(
            zip(("app_label", "model_name"), (instance.model._meta.app_label, instance.model._meta.model_name))
        )
        return {
            "model": model,
            "field": field,
        }
