from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse


def endpoint(instance_or_model, action, **params):
    action = action.replace("_", "-").lower()
    opt = instance_or_model._meta
    name = f"api-{opt.app_label}-{opt.model_name}-{action}"
    kwargs = {**params}
    if getattr(instance_or_model, "id", None):
        kwargs["pk"] = instance_or_model.id
    return reverse(name, kwargs=kwargs)


def absolute_path(path, request=None):
    if request:
        return request.build_absolute_uri(path)
    current_site = get_current_site(None)
    return f"https://{current_site.domain}{path}"


def endpoint_url(instance_or_model, action, request=None, **params):
    path = endpoint(instance_or_model, action, **params)
    return absolute_path(path, request=request)
