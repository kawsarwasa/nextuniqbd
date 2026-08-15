from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView

from category.models import Product
from sitepages.permissions import DashboardPermissionMixin

from .forms import PurchaseForm, PurchaseItemEditFormSet, PurchaseItemForm, PurchaseItemFormSet
from .models import Purchase
from .services import delete_received_purchase, sync_received_purchase_stock


def build_purchase_dashboard_stats():
    purchases = Purchase.objects.all()
    return {
        "purchase_total": purchases.count(),
        "purchase_amount_total": purchases.aggregate(total=Sum("total_amount"))["total"] or 0,
    }


def build_purchase_product_options():
    products = Product.objects.select_related("category", "brand").order_by("name", "id")
    return [
        {
            "id": product.pk,
            "label": PurchaseItemForm.build_product_label(product),
            "category": product.category.name if product.category_id else "Other products",
            "unit_price": product.current_price,
        }
        for product in products
    ]


class PurchaseDashboardMixin(DashboardPermissionMixin):
    model = Purchase
    success_url = reverse_lazy("dashboard_purchase_list")
    permission_required = "purchase.view_purchase"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_purchase_dashboard_stats())
        return context


class PurchaseListView(PurchaseDashboardMixin, ListView):
    context_object_name = "purchases"
    paginate_by = 20
    template_name = "dashboard/purchases/list.html"

    def get_queryset(self):
        return Purchase.objects.prefetch_related("items").order_by("-purchase_date", "-id")


class PurchaseDetailView(PurchaseDashboardMixin, DetailView):
    context_object_name = "purchase"
    template_name = "dashboard/purchases/detail.html"

    def get_queryset(self):
        return Purchase.objects.select_related("category", "brand").prefetch_related("items__product")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Purchase {self.object.purchase_id}"
        return context


class PurchaseCreateView(DashboardPermissionMixin, View):
    permission_required = "purchase.add_purchase"
    template_name = "dashboard/purchases/form.html"

    def get(self, request):
        form = PurchaseForm()
        item_formset = PurchaseItemFormSet(prefix="items")
        return render(request, self.template_name, self.build_context(form, item_formset, page_title="Add Purchase", submit_label="Save Purchase"))

    def post(self, request):
        form = PurchaseForm(request.POST)
        item_formset = PurchaseItemFormSet(request.POST, prefix="items")
        if form.is_valid() and item_formset.is_valid():
            with transaction.atomic():
                purchase = form.save()
                item_formset.instance = purchase
                item_formset.save()
                purchase.refresh_total()
                sync_received_purchase_stock(purchase.pk, user=request.user)
            messages.success(request, "Purchase created successfully.", extra_tags="toast-create")
            return redirect("dashboard_purchase_list")

        return render(request, self.template_name, self.build_context(form, item_formset, page_title="Add Purchase", submit_label="Save Purchase"))

    def build_context(self, form, item_formset, **extra):
        context = {
            "form": form,
            "item_formset": item_formset,
            "purchase_product_options": build_purchase_product_options(),
        }
        context.update(build_purchase_dashboard_stats())
        context.update(extra)
        return context


class PurchaseUpdateView(DashboardPermissionMixin, View):
    permission_required = "purchase.change_purchase"
    template_name = "dashboard/purchases/form.html"

    def get_object(self, pk):
        return get_object_or_404(Purchase.objects.prefetch_related("items"), pk=pk)

    def get(self, request, pk):
        purchase = self.get_object(pk)
        form = PurchaseForm(instance=purchase)
        item_formset = PurchaseItemEditFormSet(instance=purchase, prefix="items")
        return render(
            request,
            self.template_name,
            self.build_context(form, item_formset, purchase, page_title=f"Edit Purchase {purchase.purchase_id}", submit_label="Update Purchase"),
        )

    def post(self, request, pk):
        purchase = self.get_object(pk)
        form = PurchaseForm(request.POST, instance=purchase)
        item_formset = PurchaseItemEditFormSet(request.POST, instance=purchase, prefix="items")
        if form.is_valid() and item_formset.is_valid():
            try:
                with transaction.atomic():
                    locked_purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
                    for field_name in form.Meta.fields:
                        setattr(locked_purchase, field_name, form.cleaned_data[field_name])
                    item_formset.instance = locked_purchase
                    list(locked_purchase.items.select_for_update())
                    locked_purchase.save()
                    purchase = locked_purchase
                    item_formset.save()
                    purchase.refresh_total()
                    sync_received_purchase_stock(purchase.pk, user=request.user)
            except ValidationError as error:
                form.add_error(None, error)
                return render(
                    request,
                    self.template_name,
                    self.build_context(form, item_formset, purchase, page_title=f"Edit Purchase {purchase.purchase_id}", submit_label="Update Purchase"),
                )
            messages.info(request, "Purchase updated successfully.", extra_tags="toast-edit")
            return redirect("dashboard_purchase_list")

        return render(
            request,
            self.template_name,
            self.build_context(form, item_formset, purchase, page_title=f"Edit Purchase {purchase.purchase_id}", submit_label="Update Purchase"),
        )

    def build_context(self, form, item_formset, purchase, **extra):
        context = {
            "form": form,
            "item_formset": item_formset,
            "purchase": purchase,
            "purchase_product_options": build_purchase_product_options(),
        }
        context.update(build_purchase_dashboard_stats())
        context.update(extra)
        return context


class PurchaseDeleteView(DashboardPermissionMixin, View):
    permission_required = "purchase.delete_purchase"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                purchase = get_object_or_404(Purchase.objects.select_for_update(), pk=pk)
                purchase_label = purchase.purchase_id
                delete_received_purchase(purchase.pk, user=request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("dashboard_purchase_list")
        messages.error(request, f'"{purchase_label}" deleted successfully.', extra_tags="toast-delete")
        return redirect("dashboard_purchase_list")
