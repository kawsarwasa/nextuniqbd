from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from sitepages.permissions import DashboardAccessMixin, DashboardPermissionMixin, get_managed_permission_ids
from sitepages.permissions import get_permission_ids_for_cells, get_role_profile
from sitepages.views import (
    build_dashboard_profile_context,
    build_dashboard_role_list_context,
    build_dashboard_role_permission_context,
    build_dashboard_user_context,
    get_dashboard_profile,
)

from .forms import DashboardPasswordForm, DashboardProfileForm, RoleForm


User = get_user_model()


class DashboardProfileView(DashboardAccessMixin, View):
    template_name = "dashboard/profile.html"

    def get(self, request):
        return render(request, self.template_name, build_dashboard_profile_context(request.user))

    def post(self, request):
        profile = get_dashboard_profile(request.user)
        action = request.POST.get("form_type")

        if action == "password":
            password_form = DashboardPasswordForm(user=request.user, data=request.POST)
            profile_form = DashboardProfileForm(user=request.user, instance=profile)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.", extra_tags="toast-edit")
                return redirect("dashboard_profile")
            return render(
                request,
                self.template_name,
                build_dashboard_profile_context(request.user, profile_form=profile_form, password_form=password_form),
            )

        profile_form = DashboardProfileForm(request.POST, request.FILES, user=request.user, instance=profile)
        password_form = DashboardPasswordForm(user=request.user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile updated successfully.", extra_tags="toast-edit")
            return redirect("dashboard_profile")
        return render(
            request,
            self.template_name,
            build_dashboard_profile_context(request.user, profile_form=profile_form, password_form=password_form),
        )


class DashboardUserListView(DashboardPermissionMixin, ListView):
    model = User
    context_object_name = "users"
    paginate_by = 20
    permission_required = "auth.view_user"
    template_name = "dashboard/users/list.html"

    def get_queryset(self):
        return User.objects.prefetch_related("groups").order_by("-date_joined", "-id")

    def get_context_data(self, **kwargs):
        from sitepages.permissions import ensure_default_roles

        ensure_default_roles()
        context = super().get_context_data(**kwargs)
        for user in context["users"]:
            user.display_name = user.get_full_name().strip() or user.email or user.username
            user.primary_role = user.groups.order_by("name").first()
            user.primary_role_profile = get_role_profile(user.primary_role) if user.primary_role else None

        context["user_total"] = User.objects.count()
        context["user_active_total"] = User.objects.filter(is_active=True).count()
        context["role_total"] = Group.objects.count()
        return context


class DashboardUserStatusToggleView(DashboardPermissionMixin, View):
    permission_required = "auth.change_user"

    def post(self, request, pk):
        target_user = get_object_or_404(User, pk=pk)
        if target_user.is_superuser and request.user.pk != target_user.pk:
            messages.error(request, "Superuser status must be managed from the account itself.")
            return redirect("dashboard_user_list")

        target_user.is_active = request.POST.get("is_active") == "on"
        target_user.save(update_fields=["is_active"])
        messages.info(request, "User status updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_user_list")


class DashboardUserPermissionView(DashboardPermissionMixin, View):
    permission_required = ("auth.view_user", "auth.change_user", "auth.change_group")
    template_name = "dashboard/users/permissions.html"

    def get_selected_role(self, user, role_id=None):
        if role_id and str(role_id).isdigit():
            return Group.objects.filter(pk=int(role_id)).first()
        return user.groups.order_by("name").first() or Group.objects.order_by("name").first()

    def get(self, request, pk):
        target_user = get_object_or_404(User.objects.prefetch_related("groups", "user_permissions"), pk=pk)
        selected_role = self.get_selected_role(target_user, request.GET.get("role"))
        context = build_dashboard_user_context(target_user, selected_role)
        return render(request, self.template_name, context)

    def post(self, request, pk):
        target_user = get_object_or_404(User.objects.prefetch_related("groups", "user_permissions"), pk=pk)
        selected_role = self.get_selected_role(target_user, request.POST.get("role"))
        managed_permission_ids = get_managed_permission_ids()
        selected_permission_ids = get_permission_ids_for_cells(request.POST.getlist("permission_cells"))
        selected_permission_ids &= managed_permission_ids
        preserved_permission_ids = set(
            target_user.user_permissions.exclude(id__in=managed_permission_ids).values_list("id", flat=True)
        )

        target_user.is_active = request.POST.get("is_active") == "on"
        target_user.is_staff = request.POST.get("is_staff") == "on"
        target_user.save(update_fields=["is_active", "is_staff"])
        target_user.groups.set([selected_role] if selected_role else [])
        target_user.user_permissions.set(sorted(preserved_permission_ids | selected_permission_ids))

        messages.success(request, "User permissions updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_user_list")


class DashboardRoleListView(DashboardPermissionMixin, View):
    permission_required = "auth.view_group"
    template_name = "dashboard/users/roles.html"

    def get_edit_role(self, role_id):
        if role_id and str(role_id).isdigit():
            return Group.objects.select_related("role_profile").filter(pk=int(role_id)).first()
        return None

    def get(self, request):
        edit_role = self.get_edit_role(request.GET.get("edit"))
        form = RoleForm(role=edit_role)
        return render(
            request,
            self.template_name,
            build_dashboard_role_list_context(form, edit_role, request=request, page_number=request.GET.get("page")),
        )

    def post(self, request):
        edit_role = self.get_edit_role(request.POST.get("role_id"))
        if edit_role and get_role_profile(edit_role).is_system and request.POST.get("action") == "delete":
            messages.error(request, "System roles cannot be deleted.")
            form = RoleForm(role=edit_role)
            return render(request, self.template_name, build_dashboard_role_list_context(form, edit_role, request=request))

        if request.POST.get("action") == "delete" and edit_role:
            edit_role.delete()
            messages.error(request, "Role deleted successfully.", extra_tags="toast-delete")
            return redirect("dashboard_role_list")

        form = RoleForm(request.POST, role=edit_role)
        if form.is_valid():
            form.save()
            messages.success(request, "Role saved successfully.", extra_tags="toast-edit")
            return redirect("dashboard_role_list")
        return render(request, self.template_name, build_dashboard_role_list_context(form, edit_role, request=request))


class DashboardRoleStatusToggleView(DashboardPermissionMixin, View):
    permission_required = "auth.change_group"

    def post(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile"), pk=pk)
        profile = get_role_profile(role)
        profile.is_active = request.POST.get("is_active") == "on"
        profile.save(update_fields=["is_active", "updated_at"])
        messages.info(request, "Role status updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_role_list")


class DashboardRolePermissionView(DashboardPermissionMixin, View):
    permission_required = ("auth.view_group", "auth.change_group")
    template_name = "dashboard/users/role_permissions.html"

    def get(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile").prefetch_related("permissions"), pk=pk)
        return render(request, self.template_name, build_dashboard_role_permission_context(role))

    def post(self, request, pk):
        role = get_object_or_404(Group.objects.select_related("role_profile").prefetch_related("permissions"), pk=pk)
        managed_permission_ids = get_managed_permission_ids()
        selected_permission_ids = get_permission_ids_for_cells(request.POST.getlist("permission_cells"))
        selected_permission_ids &= managed_permission_ids
        preserved_permission_ids = set(role.permissions.exclude(id__in=managed_permission_ids).values_list("id", flat=True))
        role.permissions.set(sorted(preserved_permission_ids | selected_permission_ids))

        messages.success(request, "Role permissions updated successfully.", extra_tags="toast-edit")
        return redirect("dashboard_role_list")
