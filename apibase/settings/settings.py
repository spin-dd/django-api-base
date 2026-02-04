from django.conf import settings as dj_settings
from django.utils.module_loading import import_string


def perform_import(val, setting_name):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if val is None:
        return None
    elif isinstance(val, str):
        return import_from_string(val, setting_name)
    elif isinstance(val, (list, tuple)):
        return [import_from_string(item, setting_name) for item in val]
    return val


def import_from_string(val, setting_name):
    """
    Attempt to import a class from a string representation.
    """
    try:
        return import_string(val)
    except ImportError as e:
        msg = "Could not import '%s' for API setting '%s'. %s: %s." % (val, setting_name, e.__class__.__name__, e)
        raise ImportError(msg)


class Settings:
    """base DRF APISettings"""

    def __init__(self, user_settings=None, defaults=None, import_strings=None):
        self.user_settings = user_settings or {}
        self.defaults = defaults or {}
        self.import_strings = import_strings or {}
        self._cached_attrs = set()

    def __getattr__(self, attr):
        if attr not in self.defaults:
            raise AttributeError("Invalid API setting: '%s'" % attr)

        val = self.user_settings.get(attr, None)
        val_default = self.defaults.get(attr, None)

        if val_default and isinstance(val, dict):
            val = {**val_default, **val}
        else:
            val = val or val_default

        # Coerce import strings into classes
        if attr in self.import_strings:
            val = perform_import(val, attr)

        # Cache the result
        self._cached_attrs.add(attr)
        setattr(self, attr, val)
        return val

    @classmethod
    def create(cls, name, default_tuple):
        return cls(
            getattr(dj_settings, name, None),
            dict((i[0], i[1][1]) for i in default_tuple),
            [i[0] for i in default_tuple if i[1][0]],
        )
