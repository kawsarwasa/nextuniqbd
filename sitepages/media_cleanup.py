"""Remove unreferenced uploaded files after model updates and deletions.

Django intentionally does not delete files when a ``FileField`` is changed or
its model is removed.  Keeping the cleanup here makes that behavior consistent
for every app while deferring deletion until the database transaction commits.
"""

from django.apps import apps
from django.db import transaction
from django.db.models import FileField
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver


def _file_fields(model):
    return [field for field in model._meta.local_fields if isinstance(field, FileField)]


def _file_name(value):
    return getattr(value, "name", None) or None


def _is_still_referenced(file_name, using):
    """Return whether any model file field still points at ``file_name``."""
    for model in apps.get_models():
        for field in _file_fields(model):
            if model._default_manager.using(using).filter(**{field.name: file_name}).exists():
                return True
    return False


def _delete_if_unreferenced(file_name, storage, using):
    if not file_name or _is_still_referenced(file_name, using):
        return
    if storage.exists(file_name):
        storage.delete(file_name)


@receiver(pre_save)
def remember_replaced_files(sender, instance, raw=False, using=None, update_fields=None, **kwargs):
    """Remember old file names before an existing row is changed."""
    if raw or instance._state.adding:
        return

    fields = _file_fields(sender)
    if update_fields is not None:
        fields = [
            field
            for field in fields
            if field.name in update_fields or field.attname in update_fields
        ]
    if not fields:
        return

    previous = sender._default_manager.using(using).filter(pk=instance.pk).values(
        *[field.name for field in fields]
    ).first()
    if previous is None:
        return

    replaced = []
    for field in fields:
        old_name = previous[field.name] or None
        new_name = _file_name(getattr(instance, field.name))
        if old_name and old_name != new_name:
            replaced.append((old_name, field.storage))

    if replaced:
        instance._revo_replaced_files = replaced


@receiver(post_save)
def delete_replaced_files(sender, instance, using=None, **kwargs):
    """Delete previous uploads only after their replacement has committed."""
    for file_name, storage in getattr(instance, "_revo_replaced_files", []):
        transaction.on_commit(
            lambda name=file_name, file_storage=storage, db=using: _delete_if_unreferenced(
                name, file_storage, db
            ),
            using=using,
        )
    instance._revo_replaced_files = []


@receiver(post_delete)
def delete_removed_model_files(sender, instance, using=None, **kwargs):
    """Delete uploaded files when their model, including cascades, is removed."""
    for field in _file_fields(sender):
        file_name = _file_name(getattr(instance, field.name))
        if file_name:
            transaction.on_commit(
                lambda name=file_name, storage=field.storage, db=using: _delete_if_unreferenced(
                    name, storage, db
                ),
                using=using,
            )
