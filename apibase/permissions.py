from functools import wraps
from logging import getLogger

from rest_framework import permissions

logger = getLogger(__name__)


def has_perms(func, permission, *args, **kwargs):
    def wrapper(func):
        @wraps(func)
        def wrapped(self, info, *func_args, **func_kwargs):
            if not info.context.user.has_perm(permission):
                return None
            return func(self, info, *func_args, **func_kwargs)

        return wrapped

    return wrapper


def is_safe_method(request):
    return request.method in permissions.SAFE_METHODS


class Permission(permissions.IsAuthenticated):
    PERM_CODE = None
    PRIVATE = True

    @classmethod
    def has(cls, func):
        @wraps(func)
        def wrapped(self, info, *func_args, **func_kwargs):
            if not cls.check_info(info, *func_args, **func_kwargs):
                return None
            return func(self, info, *func_args, **func_kwargs)

        return wrapped

    @classmethod
    def check_info(cls, info, *args, **kwargs):
        return info.context.user.has_perm(cls.PERM_CODE)

    def has_permission(self, request, view):
        if not request.user:
            return False
        isvalid = False if self.PRIVATE else (request.method in permissions.SAFE_METHODS)
        isvalid = isvalid or request.user.has_perm(self.PERM_CODE)
        if not isvalid:
            logger.info(f"{request.user} has not {self.PERM_CODE}")
        return isvalid

    def has_query_permission(self, queryset, info, permcode=None):
        """check for graphql query"""
        permcode = permcode or self.PERM_CODE
        user = info.context.user
        if not self.PRIVATE or user.is_staff or user.has_perm(permcode):
            return True
        return False


class IsAuthenticatedOrOptions(permissions.IsAuthenticated):
    """`IsAuthenticated`, but never challenges OPTIONS.

    DRF checks permissions before it picks a handler: `APIView.dispatch` calls
    `initial()` — which runs `perform_authentication` then `check_permissions` —
    and only afterwards looks up the method handler. So plain `IsAuthenticated`
    rejects an unauthenticated OPTIONS before `APIView.options` ever runs, and
    the endpoint cannot be discovered without credentials. RFC 7231 §4.3.7
    describes OPTIONS as a capability probe, so requiring auth for it is wrong.

    Note this only relaxes the *permission* check. `perform_authentication`
    still runs first, so an authenticator that raises on bad credentials
    (token/JWT flavours) keeps failing OPTIONS requests that carry a broken
    credential. Credential-less probes — the case this exists for — are
    unaffected, since the default authenticators return `None` rather than raise.
    """

    def has_permission(self, request, view):
        if request.method == "OPTIONS":
            return True
        return super().has_permission(request, view)
