from rest_framework.routers import DefaultRouter as DrfDefaultRouter


class DefaultRouter(DrfDefaultRouter):
    def get_default_basename(self, viewset):
        """Generate defautl 'basename'"""
        queryset = getattr(viewset, "queryset", None)
        if queryset is None:
            app_label = viewset.__module__.split(".")[0]
            object_name = viewset.__name__.lower().replace("viewset", "")
        else:
            object_name = queryset.model._meta.object_name.lower()
            app_label = queryset.model._meta.app_label.lower()
        return f"api-{app_label}-{object_name}"

    def __init__(self, *args, **kwargs):
        self.root_view_name = kwargs.pop("root_view_name", self.root_view_name)
        super().__init__(*args, **kwargs)
