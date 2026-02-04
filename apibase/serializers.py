import inspect
import re

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.db.models.fields.reverse_related import OneToOneRel
from django.http import QueryDict
from django.urls import reverse
from rest_framework import exceptions, fields, serializers
from rest_framework.fields import empty

from .urn import model_urn, rest_endpoint_from_urn


def to_urn(instance, nss=None, nid=None):
    return model_urn(instance, nss=nss, nid=nid)


def endpoint_from_urn(urn, domain=None, nid=None, prefix="/api/rest", request=None):
    return rest_endpoint_from_urn(urn, domain=domain, nid=nid, prefix=prefix, request=request)


def drf_endpoint(instance, url_name=None, pk_name="pk"):
    """DRF endpoint"""
    try:
        if hasattr(instance, "get_endpoint_url"):
            return instance.get_endpoint_url()
        name = url_name or f"api-{instance._meta.app_label}-{instance._meta.model_name}-detail"
        return reverse(name, kwargs={pk_name: instance.pk})
    except Exception:
        pass
    return ""


class EndpointField(fields.Field):
    def __init__(self, **kwargs):
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        self.url_name = kwargs.get("url_name", None)
        self.attr_name = kwargs.get("attr_name", None)
        super().__init__(**kwargs)

    def get_url_name(self, value):
        return self.url_name

    def to_representation(self, value):
        instance = self.attr_name and getattr(value, self.attr_name, None) or value
        url = drf_endpoint(instance, url_name=self.get_url_name(value))
        request = self.context.get("request", None)
        return (request and url) and request.build_absolute_uri(url) or url or None


class UrnField(fields.Field):
    def __init__(self, **kwargs):
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        self.attr_name = kwargs.get("attr_name", None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        instance = self.attr_name and getattr(value, self.attr_name, None) or value
        return to_urn(instance)


class DisplayField(fields.Field):
    def __init__(self, **kwargs):
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        self.attr_name = kwargs.get("attr_name", None)
        super().__init__(**kwargs)

    def to_representation(self, value):
        instance = self.attr_name and getattr(value, self.attr_name, None) or value
        return str(instance)


class BaseModelSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    endpoint = EndpointField()
    urn = UrnField()
    display = DisplayField()

    nested_fields = []
    nested_fields_updateds_signal = None

    action_handlers = {}

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self._actions = dict((k, v(self)) for k, v in self.action_handlers.items())

    def _get_action(self, name):
        action = self._actions.get(name, None) or self._actions.get("*", None)
        return action

    def _validate_for_action(self):
        action = self._get_action(self.view_action)
        action and action.validate()

    def _save_for_action(self):
        action = self._get_action(self.view_action)
        if action:
            return action.save(super())
        return super().save()

    def is_valid(self, raise_exception=False):
        """(override)"""
        res = super().is_valid(raise_exception=raise_exception)
        res and self._validate_for_action()
        return res

    def save(self, **kwargs):
        """(override)"""
        return self._save_for_action(**kwargs)

    @property
    def children_set(self):
        return getattr(self, "_children_set", {})

    def get_children(self, name):
        return self.children_set.get(name, []) or []

    def to_representation(self, instance):
        """(override)"""
        data = super().to_representation(instance)
        if hasattr(self, "patch_result"):
            self.patch_result(instance, data)
        return data

    def run_validation_querydict(self, data=empty):
        self._children_set = QueryDict("", mutable=True, encoding=data.encoding)
        copied = QueryDict("", mutable=True, encoding=data.encoding)

        for key, value in data.lists():
            if key in self.nested_fields:
                self._children_set.setlist(key, value)
            else:
                copied.setlist(key, value)

        data = copied
        return super().run_validation(data=data)

    def run_validation(self, data=empty):
        """(override)"""
        if data == empty:
            return super().run_validation(data=data)

        if self.nested_fields:
            if isinstance(data, QueryDict):
                return self.run_validation_querydict(data=data)
            self._children_set = dict((i, data.pop(i, None)) for i in self.nested_fields)

        return super().run_validation(data=data)

    @classmethod
    def update_or_create(cls, partial=None, id=None, context=None, **validated_data):
        instance = id and cls.Meta.model.objects.filter(id=id).first()
        serializer = cls(instance=instance, data=validated_data, partial=partial, context=context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return serializer.instance

    def patch_children(self, instance, field_name, data):
        return data

    def update_nested(self, instance, validated_data, field_name, children):
        if not children or not instance:
            return []

        name = re.sub(r"(.+)(_set)$", r"\g<1>", field_name)
        related_field = self.Meta.model._meta.get_field(name)
        remote_field_name = related_field.remote_field.name

        if isinstance(related_field, OneToOneRel):
            children = [children]
            ser = self.fields[field_name]
        else:
            ser = self.fields[field_name].child

        if isinstance(related_field, GenericRelation):
            defaults = {
                related_field.object_id_field_name: instance.id,
                related_field.content_type_field_name: ContentType.objects.get_for_model(instance),
            }
        else:
            defaults = {remote_field_name: instance.id}

        items = []
        for item in children:
            if isinstance(item, str):
                pass
            item.update(defaults)
            for key in item:
                if isinstance(item[key], Model):
                    # prevent serilizer.is_valid() -> False
                    item[key] = item[key].id

            data = self.patch_children(instance, field_name, item)
            items.append(ser.update_or_create(partial=self.partial, context=self.context, **data))
        return items

    def update_nested_field(self, field_name, instance, validated_data, children):
        results = self.update_nested(instance, validated_data, field_name, children)
        return results

    def update_nested_fields(self, instance, validated_data, children_set):
        for field_name, children in children_set.items():
            self.update_nested_field(field_name, instance, validated_data, children)

        if self.nested_fields_updateds_signal:
            self.nested_fields_updateds_signal.send(
                sender=instance._meta.model,
                instance=instance,
            )

    def validated_children_set(self, validated_data):
        children_set = getattr(self, "_children_set", [])
        children_set = children_set or dict((i, validated_data.pop(i, [])) for i in self.nested_fields)
        return children_set

    def update(self, instance, validated_data):
        children_set = self.validated_children_set(validated_data)
        instance = super().update(instance, validated_data)
        self.update_nested_fields(instance, validated_data, children_set)
        return instance

    def create(self, validated_data):
        children_set = self.validated_children_set(validated_data)
        instance = super().create(validated_data)
        self.update_nested_fields(instance, validated_data, children_set)
        return instance

    @property
    def view_action(self):
        return getattr(self.context.get("view", {}), "action", None)

    @property
    def request_user(self):
        return getattr(self.context.get("request", {}), "user", None)


class UrnModelSerializer(BaseModelSerializer):
    urn = UrnField()


class BatchSerializerMixin:
    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        id_attr = getattr(self.Meta, "update_lookup_field", "id")
        request_method = getattr(self.context.get("view").request, "method", "")

        if all(
            (
                isinstance(self.root, BatchListSerializer),
                id_attr,
                request_method in ("PUT", "PATCH"),
            )
        ):
            id_field = self.fields[id_attr]
            id_value = id_field.get_value(data)

            ret[id_attr] = id_value

        return ret


class BatchListSerializer(serializers.ListSerializer):
    update_lookup_field = "id"

    def update(self, queryset, all_validated_data):
        id_attr = getattr(self.child.Meta, "update_lookup_field", "id")

        updating = {i.pop(id_attr): i for i in all_validated_data}

        if not all(bool(i) and not inspect.isclass(i) for i in updating.keys()):
            raise exceptions.ValidationError("")

        objects_to_update = queryset.filter(
            **{
                f"{id_attr}__in": updating.keys(),
            }
        )

        if len(updating) != objects_to_update.count():
            raise exceptions.ValidationError("Could not find all objects to update.")

        updated_objects = []

        for instance in objects_to_update:
            obj_id = getattr(instance, id_attr)
            obj_validated_data = updating.get(obj_id)

            updated_objects.append(self.child.update(instance, obj_validated_data))

        return updated_objects
