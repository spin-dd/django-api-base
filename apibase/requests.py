from io import StringIO
from urllib.parse import urlparse

from django.contrib.auth.models import AnonymousUser
from django.contrib.sites.models import Site
from django.core.handlers.wsgi import WSGIRequest

DEFAULTS = {
    "REQUEST_METHOD": "GET",
    "SCRIPT_NAME": "",
    "HTTP_ACCEPT": "*/*",
    "HTTP_USER_AGENT": "MockRequest/1.0",
    "HTTP_ACCEPT_LANGUAGE": "en-US,en;q=0.8",
    "SERVER_PROTOCOL": "HTTP/1.1",
    "wsgi.input": StringIO(),
    "wsgi.multiprocess": True,
    "wsgi.multithread": False,
    "wsgi.run_once": False,
    "wsgi.version": (1, 0),
}


def create_request(url="/", user=None, params=None, site=None):
    try:
        site = site or Site.objects.get_current()
    except Exception:
        pass

    parsed_url = urlparse(url)

    scheme = parsed_url.scheme or "http"
    hostname = parsed_url.hostname or (site and site.domain or "example.com")
    port = parsed_url.port or 80

    data = {
        **DEFAULTS,
        **(params or {}),
        "REQUEST_URI": parsed_url.path,
        "PATH_INFO": parsed_url.path,
        "QUERY_STRING": parsed_url.query,
        "HTTPS": ("on" if scheme == "https" else "off"),
        "HTTP_HOST": hostname,
        "SERVER_NAME": hostname,
        "HTTP_REFERER": f"{scheme}//{hostname}/",
        "SERVER_PORT": port or (443 if scheme == "https" else 80),
        "wsgi.url_scheme": scheme or "http",
    }

    request = WSGIRequest(data)
    request.user = AnonymousUser() if user is None else user
    request.session = {}

    return request
