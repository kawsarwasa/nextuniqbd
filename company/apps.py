from django.apps import AppConfig


class CompanyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "company"

    def ready(self):
        from . import signals  # noqa: F401
