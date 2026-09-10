import os
from pathlib import Path

import ulid
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone as tz
from django.utils.deconstruct import deconstructible

from .settings import apibase_settings


@deconstructible
class LocalPathResolver:
    """file upload resolver"""

    RESOLVE_CONTNT_TYPE = True

    def __init__(self, field_name, access=""):
        self.field_name = field_name
        self.access = access
        self.content_type = None

    def __call__(self, instance, original_filename):
        self.content_type = self.resolve_content_type(instance)
        filename = self.create_path(original_filename, instance=instance)
        return self.construct_filename(instance, filename)

    def create_path(self, filename, instance=None, **kwargs):
        path = Path(filename)
        today = tz.now().strftime("%Y-%m-%d")
        return f"{today}/{ulid.new().str}{path.suffix}"

    def resolve_content_type(self, instance):
        content_type = ContentType.objects.get_for_model(instance)
        if not self.RESOLVE_CONTNT_TYPE:
            return content_type

        return self.content_type or getattr(instance, "content_type", None) or content_type

    def construct_filename(self, instance, path):
        content_type = self.resolve_content_type(instance)
        return os.path.join(
            self.access,
            content_type.app_label,
            content_type.model,
            apibase_settings.STORAGE_PREFIX,
            self.field_name,
            path,
        )

    def find_instance(self, model_class, path):
        query = {self.field_name: self.construct_filename(model_class(), path)}
        return model_class.objects.filter(**query).first()

    @classmethod
    def find(cls, model_class, field_name, path):
        field = model_class._meta.get_field(field_name)
        return field and field.upload_to.find_instance(model_class, path) or None
