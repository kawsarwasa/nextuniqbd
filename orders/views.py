from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.template.loader import render_to_string
from django.views import View

from sitepages.permissions import DashboardPermissionMixin
from sitepages.dashboard_pagination import build_dashboard_pagination_context
from sitepages.views import build_dashboard_order_detail_context, build_dashboard_order_list_context
from sitepages.views import get_visible_orders_queryset
from sitepages.models import AbandonedCheckout, Order, Sale
from sitepages.order_status import change_order_status
from sitepages.order_tracking import (
    build_order_tracking_context,
    get_order_tracking_queryset,
    user_can_access_order_tracking,
)

from .forms import OrderStatusForm


def _decorate_abandoned_checkout(checkout):
    checkout.delivery_area_label = (checkout.delivery_area or "").replace("_", " ").title() or "—"
    checkout.status_badge_class = {
        AbandonedCheckout.Status.PENDING: "text-bg-warning",
        AbandonedCheckout.Status.CONTACTED: "text-bg-info",
        AbandonedCheckout.Status.CANCELLED: "text-bg-secondary",
    }.get(checkout.status, "text-bg-secondary")
    return checkout


class DashboardOrderListView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_order"
    template_name = "dashboard/orders/list.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            build_dashboard_order_list_context(request.user, page_number=request.GET.get("page"), request=request),
        )


class DashboardOrderTrackingView(DashboardPermissionMixin, View):
    """Return timeline data only for orders visible to the current dashboard user."""

    permission_required = "sitepages.view_order"

    def get(self, request, order_id):
        if not user_can_access_order_tracking(request.user):
            raise PermissionDenied("You do not have permission to view order tracking.")

        order = get_object_or_404(get_order_tracking_queryset(), order_id=order_id)
        tracking = build_order_tracking_context(order)
        return JsonResponse(
            {
                "order_number": tracking["order_number"],
                "detail_url": tracking["detail_url"],
                "html": render_to_string(
                    "dashboard/orders/includes/tracking_timeline.html",
                    {"tracking": tracking},
                    request=request,
                ),
            }
        )


class DashboardAbandonedCheckoutListView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_sale"
    template_name = "dashboard/orders/abandoned_checkout_list.html"
    paginate_by = 20

    def get_queryset(self, request):
        queryset = (
            AbandonedCheckout.objects.select_related("user")
            .exclude(status=AbandonedCheckout.Status.CONVERTED)
        )

        search = request.GET.get("q", "").strip()
        district = request.GET.get("district", "").strip()
        user_type = request.GET.get("user_type", "").strip()
        status = request.GET.get("status", AbandonedCheckout.Status.PENDING).strip()
        date_from = request.GET.get("date_from", "").strip()
        date_to = request.GET.get("date_to", "").strip()
        parsed_date_from = parse_date(date_from)
        parsed_date_to = parse_date(date_to)

        allowed_statuses = {
            AbandonedCheckout.Status.PENDING,
            AbandonedCheckout.Status.CONTACTED,
            AbandonedCheckout.Status.CANCELLED,
        }
        if status not in allowed_statuses:
            status = AbandonedCheckout.Status.PENDING

        queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(email__icontains=search)
            )
        if district:
            queryset = queryset.filter(district=district)
        if user_type == "registered":
            queryset = queryset.filter(user__isnull=False)
        elif user_type == "guest":
            queryset = queryset.filter(user__isnull=True)
        if parsed_date_from:
            queryset = queryset.filter(created_at__date__gte=parsed_date_from)
        else:
            date_from = ""
        if parsed_date_to:
            queryset = queryset.filter(created_at__date__lte=parsed_date_to)
        else:
            date_to = ""

        return queryset.order_by("-created_at", "-id"), {
            "q": search,
            "district": district,
            "user_type": user_type,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
        }

    def get(self, request):
        queryset, filters = self.get_queryset(request)
        paginator = Paginator(queryset, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))
        for abandoned_checkout in page_obj.object_list:
            _decorate_abandoned_checkout(abandoned_checkout)
        return render(
            request,
            self.template_name,
            {
                "abandoned_checkouts": page_obj.object_list,
                "page_obj": page_obj,
                "abandoned_checkout_total": paginator.count,
                "districts": (
                    AbandonedCheckout.objects.exclude(status=AbandonedCheckout.Status.CONVERTED)
                    .exclude(district__isnull=True)
                    .exclude(district="")
                    .order_by("district")
                    .values_list("district", flat=True)
                    .distinct()
                ),
                "status_choices": [
                    (AbandonedCheckout.Status.PENDING, "Pending"),
                    (AbandonedCheckout.Status.CONTACTED, "Contacted"),
                    (AbandonedCheckout.Status.CANCELLED, "Cancelled"),
                ],
                "filters": filters,
                **build_dashboard_pagination_context(request, page_obj),
            },
        )


class DashboardAbandonedCheckoutDetailView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_sale"
    template_name = "dashboard/orders/abandoned_checkout_detail.html"

    def get(self, request, pk):
        abandoned_checkout = get_object_or_404(
            AbandonedCheckout.objects.select_related("user").exclude(
                status=AbandonedCheckout.Status.CONVERTED
            ),
            pk=pk,
        )
        _decorate_abandoned_checkout(abandoned_checkout)
        return render(
            request,
            self.template_name,
            {
                "abandoned_checkout": abandoned_checkout,
                "cart_items": abandoned_checkout.cart_items,
            },
        )


class DashboardAbandonedCheckoutStatusView(DashboardPermissionMixin, View):
    permission_required = "sitepages.change_sale"

    @transaction.atomic
    def post(self, request, pk, status):
        allowed_statuses = {
            AbandonedCheckout.Status.CONTACTED,
            AbandonedCheckout.Status.CANCELLED,
        }
        if status not in allowed_statuses:
            messages.error(request, "Invalid abandoned checkout status.")
            return redirect("dashboard_abandoned_checkout_detail", pk=pk)

        abandoned_checkout = get_object_or_404(
            AbandonedCheckout.objects.select_for_update().exclude(
                status=AbandonedCheckout.Status.CONVERTED
            ),
            pk=pk,
        )
        abandoned_checkout.status = status
        abandoned_checkout.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Abandoned checkout marked as {abandoned_checkout.get_status_display().lower()}.",
            extra_tags="toast-edit",
        )

        redirect_to = request.POST.get("next", "")
        if redirect_to == "list":
            return redirect("dashboard_abandoned_checkout_list")
        return redirect("dashboard_abandoned_checkout_detail", pk=pk)


class DashboardSaleListView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_sale"
    template_name = "dashboard/sales/list.html"
    paginate_by = 20

    def get_queryset(self, user):
        queryset = (
            Sale.objects.select_related("user")
            .prefetch_related("items")
            .order_by("-sale_date", "-id")
        )
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(user=user)

    def get(self, request):
        sales_queryset = self.get_queryset(request.user)
        sale_stats = sales_queryset.aggregate(
            sale_amount_total=Sum("total_amount"),
            sale_item_total=Sum("item_count"),
        )
        paginator = Paginator(sales_queryset, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))
        sales = list(page_obj.object_list)
        sale_amount_total = sale_stats["sale_amount_total"] or Decimal("0")
        context = {
            "sales": sales,
            "page_obj": page_obj,
            "sale_total": paginator.count,
            "sale_amount_total": sale_amount_total,
            "sale_item_total": sale_stats["sale_item_total"] or 0,
            "average_sale_amount": (
                sale_amount_total / paginator.count
                if paginator.count
                else 0
            ),
        }
        context.update(build_dashboard_pagination_context(request, page_obj))
        return render(request, self.template_name, context)


class DashboardSaleDetailView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_sale"
    template_name = "dashboard/sales/detail.html"

    def get_queryset(self, user):
        queryset = Sale.objects.select_related("user").prefetch_related("items").order_by("-sale_date", "-id")
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return queryset
        return queryset.filter(user=user)

    def get(self, request, sale_id):
        sale = get_object_or_404(self.get_queryset(request.user), sale_id=sale_id)
        return render(
            request,
            self.template_name,
            {
                "sale": sale,
                "sale_items": list(sale.items.all()),
            },
        )


class DashboardOrderDetailView(DashboardPermissionMixin, View):
    permission_required = "sitepages.view_order"
    template_name = "dashboard/orders/detail.html"

    def get(self, request, order_id):
        order = get_object_or_404(get_visible_orders_queryset(request.user), order_id=order_id)
        return render(
            request,
            self.template_name,
            build_dashboard_order_detail_context(
                order,
                include_tracking=user_can_access_order_tracking(request.user),
            ),
        )

    def post(self, request, order_id):
        order_queryset = Order.objects.select_related("user")
        if not (request.user.is_staff or request.user.is_superuser):
            order_queryset = order_queryset.filter(user=request.user)
        order = get_object_or_404(order_queryset, order_id=order_id)
        if not (request.user.is_superuser or request.user.has_perm("sitepages.change_order")):
            messages.error(request, "You do not have permission to update this order.")
            return redirect("dashboard_order_detail", order_id=order.order_id)

        status_form = OrderStatusForm(request.POST, order=order)
        if status_form.is_valid():
            new_status = status_form.cleaned_data["status"]
            try:
                status_change = change_order_status(
                    order=order,
                    new_status=new_status,
                    changed_by=request.user,
                    note=status_form.cleaned_data["note"],
                    source="dashboard",
                )
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("dashboard_order_detail", order_id=order.order_id)

            if not status_change.changed:
                messages.info(request, "Order status was already set to that value.", extra_tags="toast-edit")
            elif new_status == Order.Status.CONFIRMED:
                messages.success(request, "Order confirmed and sale generated successfully.", extra_tags="toast-edit")
            elif new_status == Order.Status.CANCELLED:
                messages.success(request, "Order cancelled and stock restored successfully.", extra_tags="toast-edit")
            elif new_status == Order.Status.RETURNED:
                messages.success(request, "Order marked as returned and stock restored successfully.", extra_tags="toast-edit")
            else:
                messages.success(request, "Order status updated successfully.", extra_tags="toast-edit")
            return redirect("dashboard_order_detail", order_id=order.order_id)

        return render(
            request,
            self.template_name,
            build_dashboard_order_detail_context(
                order,
                status_form=status_form,
                include_tracking=user_can_access_order_tracking(request.user),
            ),
        )
