from logging import getLogger
from pathlib import Path

from django.contrib.auth.models import Permission
from django.http import Http404
from django.utils.functional import cached_property
from django.views import static
from rest_framework import decorators, serializers, status, viewsets
from rest_framework.response import Response

from . import paginations, permissions, storages, utils
from .settings import apibase_settings

logger = getLogger()


class ViewSetMixin:
    @classmethod
    def permissions(cls):
        return [
            Permission.objects.filter(
                **dict(zip(("content_type__app_label", "codename"), p.PERM_CODE.split(".")))
            ).first()
            for p in cls.permission_classes
            if issubclass(p, permissions.Permission) and p.PERM_CODE
        ]

    @property
    def is_safe_method(self):
        return permissions.is_safe_method(self.request)


def static_serve(request, path, name=None, document_root="/"):
    response = static.serve(request, path, document_root=document_root)
    if name:
        response["Content-Disposition"] = utils.to_content_disposition(name)
    return response


class DownloadMixin:
    @decorators.action(methods=["get"], detail=True, url_path="(?P<field>[^/.]+)/download")
    def download_filefield(self, request, pk, format=None, field=None):
        """download FileField file"""
        instance = self.get_object()
        return self.response_field_data(request, instance, field)

    @decorators.action(
        methods=["get"],
        detail=False,
        url_path=rf"{apibase_settings.STORAGE_PREFIX}/?(?P<field>[^/\d]+)/(?P<name>.+)",
    )
    def download_filefield_storage(self, request, field=None, name=None, format=None):
        path = f"{name}.{format}" if format else name
        instance = storages.LocalPathResolver.find(self.queryset.model, field, path)
        return self.response_field_data(request, instance, field)

    def response_field_data(self, request, instance, field):
        try:
            field = getattr(instance, field, None)
            disposition = utils.to_content_disposition(self.get_download_filefield_name(instance, field))
        except Exception as e:
            logger.error(f"DownloadMixin.response_field_data:{e}")
            raise Http404

        res = self.create_download_filefield_response(request, instance, field, format=format)
        res["Content-Disposition"] = disposition
        return res

    def create_download_filefield_response(self, request, instance, field, format=None):
        return static.serve(
            request,
            field.path,
            document_root="/",
        )

    def get_download_filefield_name(self, instance, field):
        name = str(instance)
        ext = Path(field.path).suffix
        return f"{field.field.verbose_name}.{name}{ext}"


class BaseModelViewSet(viewsets.ModelViewSet, ViewSetMixin, DownloadMixin):
    pagination_class = paginations.Pagination
    fields_query = None

    @decorators.action(methods=["post"], detail=False)
    def batch_create(self, request, *args, **kwargs):
        if request.method == "GET":
            return self.list(request)
        return self.create(request, many=True)

    @decorators.action(methods=["patch", "get"], detail=False)
    def batch_update(self, request):
        if request.method == "GET":
            return self.list(request)
        return self.update(request, pk=None, many=True, partial=True)

    def update(self, request, *args, **kwargs):
        """(override)"""
        many = kwargs.pop("many", False)
        if many:
            return self.update_batch(request, *args, **kwargs)
        return super().update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """(override)"""
        many = kwargs.pop("many", False)
        if many:
            return self.create_batch(request, *args, **kwargs)
        return super().create(request, *args, **kwargs)

    def update_batch(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def create_batch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def paginate_queryset(self, queryset):
        """(override)"""
        # dirty coding for CSV rendering
        if self.request.META.get("HTTP_ACCEPT", None) == "text/csv":
            return None
        return super().paginate_queryset(queryset)

    def get_serializer(self, *args, **kwargs):
        """(override)"""
        ser = super().get_serializer(*args, **kwargs)

        if isinstance(ser, serializers.ListSerializer):
            self._fields = ser.child.fields
        else:
            self._fields = ser.fields
        return ser

    @cached_property
    def label_map(self):
        fields = getattr(self, "_fields", {})
        return dict((name, f.label) for name, f in fields.items())

    def get_renderer_context(self):
        """(override)"""
        fields_query = getattr(self, "fields_query", None)

        context = super().get_renderer_context()
        if not fields_query:
            return context

        if self.request.META.get("HTTP_ACCEPT", "").startswith("text/csv"):
            if self.request.encoding is None or self.request.encoding == "utf-8":
                context["encoding"] = "utf-8-sig"
            else:
                context["encoding"] = self.request.encoding

        # dirty  coding header(list) and lable(dict)
        context["header"] = self.request.GET[fields_query].split(",") if fields_query in self.request.GET else None

        context["labels"] = (
            dict((i, self.label_map.get(i, i)) for i in context["header"]) if context["header"] else self.label_map
        )

        return context
