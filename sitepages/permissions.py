from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import redirect
from django.urls import reverse_lazy

from category.models import Brand, Category, Product
from company.models import CompanyProfile
from finance.models import CashTransaction, DueAccount, DuePayment, TransactionCategory
from purchase.models import Purchase

from .dashboard_pagination import DashboardPaginationContextMixin
from .models import (
    AbandonedCheckout,
    HeroSlide,
    Order,
    RoleProfile,
    Sale,
)


User = get_user_model()

PERMISSION_ACTIONS = (
    ("view", "View"),
    ("add", "Edit"),
    ("change", "Update"),
    ("delete", "Delete"),
)

MANAGED_PERMISSION_MODULES = (
    ("user", "Users", (User,)),
    ("group", "Roles", (Group,)),
    ("category", "Category", (Category,)),
    ("brand", "Brand", (Brand,)),
    ("product", "Product", (Product,)),
    ("purchase", "Purchase", (Purchase,)),
    ("order", "Orders", (Order, Sale, AbandonedCheckout)),
    ("heroslide", "Carousel", (HeroSlide,)),
    ("company", "Company", (CompanyProfile,)),
    ("accounts", "Accounts", (TransactionCategory, CashTransaction, DueAccount, DuePayment)),
)

ROLE_DEFINITIONS = {
    "admins": {
        "description": "Full access across the dashboard.",
        "modules": "*",
    },
    "catalog_managers": {
        "description": "Can manage catalog modules such as categories, brands, and products.",
        "modules": {"category", "brand", "product", "purchase"},
    },
    "content_managers": {
        "description": "Can manage hero slides and company content.",
        "modules": {
            "heroslide",
            "company",
        }
    },
    "customers": {
        "description": "Default storefront role with order-only dashboard access.",
        "modules": set(),
        "extra_permissions": (
            (Order, "view"),
        ),
    },
}


def _get_content_type_map():
    return {
        model: ContentType.objects.get_for_model(model)
        for _, _, models in MANAGED_PERMISSION_MODULES
        for model in models
    }


def get_managed_permission_queryset():
    content_types = _get_content_type_map().values()
    return Permission.objects.filter(content_type__in=content_types).select_related("content_type")


def get_managed_permission_ids():
    return set(get_managed_permission_queryset().values_list("id", flat=True))


def get_managed_permission_codenames():
    return list(get_managed_permission_queryset().values_list("content_type__app_label", "codename"))


def get_role_profile(role):
    if role is None:
        return None

    try:
        return role.role_profile
    except RoleProfile.DoesNotExist:
        return RoleProfile.objects.create(group=role)


def get_permission_matrix():
    content_type_map = _get_content_type_map()
    permission_lookup = {
        (permission.content_type_id, permission.codename): permission
        for permission in get_managed_permission_queryset()
    }

    rows = []
    for key, label, models in MANAGED_PERMISSION_MODULES:
        permissions = {}
        for action, _ in PERMISSION_ACTIONS:
            action_permissions = []
            for model in models:
                content_type = content_type_map[model]
                permission = permission_lookup.get((content_type.id, f"{action}_{model._meta.model_name}"))
                if permission is not None:
                    action_permissions.append(permission)
            permissions[action] = action_permissions
        rows.append({"key": key, "label": label, "permissions": permissions})
    return rows


def get_role_permission_rows(role):
    assigned_permission_ids = set()
    if role is not None:
        assigned_permission_ids = set(role.permissions.values_list("id", flat=True))

    rows = []
    for row in get_permission_matrix():
        permissions = {}
        for action, label in PERMISSION_ACTIONS:
            action_permissions = row["permissions"][action]
            permission_ids = [permission.id for permission in action_permissions]
            permissions[action] = {
                "label": label,
                "permission_ids": permission_ids,
                "input_value": f"{row['key']}:{action}",
                "checked": bool(permission_ids) and all(
                    permission_id in assigned_permission_ids for permission_id in permission_ids
                ),
            }
        rows.append({"key": row["key"], "label": row["label"], "permissions": permissions})
    return rows


def get_user_permission_rows(user, role=None):
    assigned_permission_ids = set()
    if user is not None:
        assigned_permission_ids = set(user.user_permissions.values_list("id", flat=True))

    role_permission_ids = set()
    if role is not None:
        role_permission_ids = set(role.permissions.values_list("id", flat=True))

    rows = []
    for row in get_permission_matrix():
        permissions = {}
        for action, label in PERMISSION_ACTIONS:
            action_permissions = row["permissions"][action]
            permission_ids = [permission.id for permission in action_permissions]
            granted_by_role = bool(permission_ids) and all(
                permission_id in role_permission_ids for permission_id in permission_ids
            )
            granted_directly = bool(permission_ids) and all(
                permission_id in assigned_permission_ids for permission_id in permission_ids
            )
            permissions[action] = {
                "label": label,
                "permission_ids": permission_ids,
                "input_value": f"{row['key']}:{action}",
                "checked": granted_by_role or granted_directly,
                "granted_by_role": granted_by_role,
                "granted_directly": granted_directly,
                "readonly": granted_by_role,
            }
        rows.append({"key": row["key"], "label": row["label"], "permissions": permissions})
    return rows


def get_permission_ids_for_cells(selected_cells):
    permission_matrix = {
        row["key"]: row["permissions"]
        for row in get_permission_matrix()
    }
    selected_permission_ids = set()

    for cell in selected_cells:
        module_key, separator, action = (cell or "").partition(":")
        if not separator:
            continue
        for permission in permission_matrix.get(module_key, {}).get(action, []):
            selected_permission_ids.add(permission.id)

    return selected_permission_ids


def ensure_default_roles():
    matrix = get_permission_matrix()
    permission_ids_by_module = {
        row["key"]: {
            permission.id
            for permission_list in row["permissions"].values()
            for permission in permission_list
        }
        for row in matrix
    }
    managed_permission_ids = get_managed_permission_ids()

    for role_name, config in ROLE_DEFINITIONS.items():
        role, created = Group.objects.get_or_create(name=role_name)
        profile = get_role_profile(role)
        preserved_permission_ids = set(role.permissions.exclude(id__in=managed_permission_ids).values_list("id", flat=True))
        current_managed_permission_ids = set(role.permissions.filter(id__in=managed_permission_ids).values_list("id", flat=True))

        if config["modules"] == "*":
            default_permission_ids = managed_permission_ids
        else:
            default_permission_ids = set()
            for module_key in config["modules"]:
                default_permission_ids.update(permission_ids_by_module.get(module_key, set()))
            for model, action in config.get("extra_permissions", ()):
                content_type = ContentType.objects.get_for_model(model)
                permission = Permission.objects.filter(
                    content_type=content_type,
                    codename=f"{action}_{model._meta.model_name}",
                ).first()
                if permission is not None:
                    default_permission_ids.add(permission.id)

        if created:
            role.permissions.set(sorted(preserved_permission_ids | default_permission_ids))
        elif profile.is_system:
            # Backfill newly introduced default module permissions without removing manual changes.
            role.permissions.set(sorted(preserved_permission_ids | current_managed_permission_ids | default_permission_ids))

        profile.description = config.get("description", profile.description)
        profile.is_system = True
        profile.save(update_fields=["description", "is_system", "updated_at"])


def user_can_access_dashboard(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True

    for app_label, codename in get_managed_permission_codenames():
        if user.has_perm(f"{app_label}.{codename}"):
            return True
    return False


class DashboardAccessMixin(LoginRequiredMixin):
    login_url = reverse_lazy("auth_login")
    redirect_field_name = "next"


class DashboardPermissionMixin(DashboardPaginationContextMixin, DashboardAccessMixin, PermissionRequiredMixin):
    raise_exception = False
    permission_denied_message = "You do not have permission to open that dashboard page."

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        messages.error(self.request, self.get_permission_denied_message())
        return redirect("dashboard_home")
