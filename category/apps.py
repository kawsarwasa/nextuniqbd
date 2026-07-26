from django.apps import AppConfig


class CategoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "category"

    def ready(self):
        from . import signals  # noqa: F401
