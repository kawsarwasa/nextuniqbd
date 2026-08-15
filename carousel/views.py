from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from sitepages.forms import HeroSlideForm
from sitepages.models import HeroSlide
from sitepages.permissions import DashboardPermissionMixin


class HeroSlideDashboardMixin(DashboardPermissionMixin):
    model = HeroSlide
    form_class = HeroSlideForm
    success_url = reverse_lazy("dashboard_hero_slide_list")
    permission_required = "sitepages.view_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hero_slide_total"] = HeroSlide.objects.count()
        context["hero_slide_active_total"] = HeroSlide.objects.filter(is_active=True).count()
        return context


class HeroSlideListView(HeroSlideDashboardMixin, ListView):
    context_object_name = "hero_slides"
    paginate_by = 20
    template_name = "dashboard/carousel/list.html"

    def get_queryset(self):
        return HeroSlide.objects.order_by("sort_order", "id")


class HeroSlideCreateView(HeroSlideDashboardMixin, CreateView):
    template_name = "dashboard/carousel/form.html"
    permission_required = "sitepages.add_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Hero Slide"
        context["submit_label"] = "Save Slide"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Hero slide created successfully.", extra_tags="toast-create")
        return response


class HeroSlideUpdateView(HeroSlideDashboardMixin, UpdateView):
    template_name = "dashboard/carousel/form.html"
    permission_required = "sitepages.change_heroslide"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Hero Slide"
        context["submit_label"] = "Update Slide"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Hero slide updated successfully.", extra_tags="toast-edit")
        return response


class HeroSlideDeleteView(DashboardPermissionMixin, View):
    permission_required = "sitepages.delete_heroslide"

    def post(self, request, pk):
        hero_slide = get_object_or_404(HeroSlide, pk=pk)
        slide_name = hero_slide.name
        hero_slide.delete()
        messages.error(
            request,
            f'"{slide_name}" deleted successfully.',
            extra_tags="toast-delete",
        )
        return redirect("dashboard_hero_slide_list")
