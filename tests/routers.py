"""Route the atomic-write test models to a real second database."""


class AtomicWritesRouter:
    def db_for_read(self, model, **hints):
        if model._meta.model_name in {"parent", "child"}:
            return "other"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in {"parent", "child"}:
            instance = hints.get("instance")
            return instance._state.db if instance and instance._state.db else "other"
        return None


class InstanceWritesRouter(AtomicWritesRouter):
    """Updates follow the instance; writes without a hint use the default DB."""

    def db_for_write(self, model, **hints):
        instance = hints.get("instance")
        return instance._state.db if instance else None
