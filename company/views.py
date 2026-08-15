from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from sitepages.permissions import DashboardPermissionMixin

from .forms import CompanyProfileForm
from .models import CompanyProfile


class CompanyProfileDashboardMixin(DashboardPermissionMixin):
    model = CompanyProfile
    form_class = CompanyProfileForm
    success_url = reverse_lazy("dashboard_company_profile_list")
    permission_required = "company.view_companyprofile"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["company_profile_total"] = CompanyProfile.objects.count()
        context["company_profile_active_total"] = CompanyProfile.objects.filter(is_active=True).count()
        context["company_profile"] = CompanyProfile.get_singleton()
        return context


class CompanyProfileListView(CompanyProfileDashboardMixin, ListView):
    context_object_name = "company_profiles"
    paginate_by = 20
    template_name = "dashboard/company/profile_list.html"

    def get_queryset(self):
        return CompanyProfile.objects.order_by("-logo", "-is_active", "-updated_at", "id")[:1]


class CompanyProfileCreateView(CompanyProfileDashboardMixin, CreateView):
    template_name = "dashboard/company/profile_form.html"
    permission_required = "company.add_companyprofile"

    def dispatch(self, request, *args, **kwargs):
        company_profile = CompanyProfile.get_singleton()
        if company_profile:
            messages.info(request, "Company profile already exists. Edit it instead.", extra_tags="toast-edit")
            return redirect("dashboard_company_profile_edit", pk=company_profile.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Company Profile"
        context["submit_label"] = "Save Company Profile"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Company profile created successfully.", extra_tags="toast-create")
        return response


class CompanyProfileUpdateView(CompanyProfileDashboardMixin, UpdateView):
    template_name = "dashboard/company/profile_form.html"
    permission_required = "company.change_companyprofile"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Company Profile"
        context["submit_label"] = "Update Company Profile"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Company profile updated successfully.", extra_tags="toast-edit")
        return response


class CompanyProfileDeleteView(DashboardPermissionMixin, View):
    permission_required = "company.delete_companyprofile"

    def post(self, request, pk):
        company_profile = get_object_or_404(CompanyProfile, pk=pk)
        company_name = company_profile.company_name
        company_profile.delete()
        messages.error(request, f'"{company_name}" deleted successfully.', extra_tags="toast-delete")
        return redirect("dashboard_company_profile_list")
