from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, OuterRef, ProtectedError, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from sitepages.permissions import DashboardPermissionMixin

from purchase.models import PurchaseItem

from .forms import BrandForm, CategoryForm, ProductForm
from .models import Brand, Category, Product, ProductImage, StockTransaction


def product_deletion_blockers(product):
    blockers = []
    if product.stock_transactions.exists():
        blockers.append("stock transactions")
    if product.order_items.exists() or product.order_stock_applications.exists() or product.sale_items.exists():
        blockers.append("order or sale records")
    if product.purchase_items.exists() or product.purchase_stock_applications.exists():
        blockers.append("purchase records")
    return blockers


def delete_products_safely(products):
    deleted_names = []
    blocked_products = []
    for product in products:
        blockers = product_deletion_blockers(product)
        if blockers:
            blocked_products.append((product.name, blockers))
            continue
        try:
            product.delete()
            deleted_names.append(product.name)
        except ProtectedError:
            blocked_products.append((product.name, ["protected related records"]))
    return deleted_names, blocked_products


class CategoryDashboardMixin(DashboardPermissionMixin):
    model = Category
    form_class = CategoryForm
    success_url = reverse_lazy("dashboard_category_list")
    permission_required = "category.view_category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category_total"] = Category.objects.count()
        context["category_active_total"] = Category.objects.filter(is_active=True).count()
        return context


class CategoryListView(CategoryDashboardMixin, ListView):
    context_object_name = "categories"
    paginate_by = 10
    template_name = "dashboard/categories/list.html"

    def get_queryset(self):
        return Category.objects.order_by("sort_order", "name", "id")


class CategoryCreateView(CategoryDashboardMixin, CreateView):
    template_name = "dashboard/categories/form.html"
    permission_required = "category.add_category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Category"
        context["form_mode"] = "create"
        context["submit_label"] = "Save Category"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Category created successfully.",
            extra_tags="toast-create",
        )
        return response


class CategoryUpdateView(CategoryDashboardMixin, UpdateView):
    template_name = "dashboard/categories/form.html"
    permission_required = "category.change_category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Category"
        context["form_mode"] = "edit"
        context["submit_label"] = "Update Category"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            "Category updated successfully.",
            extra_tags="toast-edit",
        )
        return response


class CategoryDeleteView(DashboardPermissionMixin, View):
    permission_required = "category.delete_category"

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        category_name = category.name
        was_deleted = category.safe_delete()

        if was_deleted:
            messages.error(
                request,
                f'"{category_name}" deleted successfully.',
                extra_tags="toast-delete",
            )
        else:
            messages.warning(
                request,
                f'"{category_name}" could not be deleted and was deactivated instead.',
                extra_tags="toast-warning",
            )

        return redirect("dashboard_category_list")


class BrandDashboardMixin(DashboardPermissionMixin):
    model = Brand
    form_class = BrandForm
    success_url = reverse_lazy("dashboard_brand_list")
    permission_required = "category.view_brand"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["brand_total"] = Brand.objects.count()
        context["brand_active_total"] = Brand.objects.filter(is_active=True).count()
        return context


class BrandListView(BrandDashboardMixin, ListView):
    context_object_name = "brands"
    paginate_by = 10
    template_name = "dashboard/brands/list.html"

    def get_queryset(self):
        return Brand.objects.order_by("-id")


class BrandCreateView(BrandDashboardMixin, CreateView):
    template_name = "dashboard/brands/form.html"
    permission_required = "category.add_brand"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Brand"
        context["form_mode"] = "create"
        context["submit_label"] = "Save Brand"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Brand created successfully.",
            extra_tags="toast-create",
        )
        return response


class BrandUpdateView(BrandDashboardMixin, UpdateView):
    template_name = "dashboard/brands/form.html"
    permission_required = "category.change_brand"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Brand"
        context["form_mode"] = "edit"
        context["submit_label"] = "Update Brand"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(
            self.request,
            "Brand updated successfully.",
            extra_tags="toast-edit",
        )
        return response


class BrandDeleteView(DashboardPermissionMixin, View):
    permission_required = "category.delete_brand"

    def post(self, request, pk):
        brand = get_object_or_404(Brand, pk=pk)
        brand_name = brand.name
        was_deleted = brand.safe_delete()

        if was_deleted:
            messages.error(
                request,
                f'"{brand_name}" deleted successfully.',
                extra_tags="toast-delete",
            )
        else:
            messages.warning(
                request,
                f'"{brand_name}" could not be deleted and was deactivated instead.',
                extra_tags="toast-warning",
            )

        return redirect("dashboard_brand_list")


class ProductDashboardMixin(DashboardPermissionMixin):
    model = Product
    form_class = ProductForm
    success_url = reverse_lazy("dashboard_product_list")
    permission_required = "category.view_product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            Product.objects.aggregate(
                product_total=Count("pk"),
                product_published_total=Count(
                    "pk",
                    filter=Q(status=Product.Status.PUBLISHED),
                ),
                product_low_stock_total=Count(
                    "pk",
                    filter=Q(
                        track_stock=True,
                        stock_quantity__gt=0,
                        stock_quantity__lte=F("low_stock_threshold"),
                    ),
                ),
                product_out_of_stock_total=Count(
                    "pk",
                    filter=Q(track_stock=True, stock_quantity=0),
                ),
            )
        )
        return context

    def sync_images(self, product, form):
        remove_images = form.cleaned_data.get("remove_images") or []
        if remove_images:
            product.images.filter(pk__in=remove_images).delete()

        next_sort_order = (
            product.images.order_by("-sort_order").values_list("sort_order", flat=True).first()
        )
        next_sort_order = 0 if next_sort_order is None else next_sort_order + 1

        for image in form.cleaned_data.get("new_images") or []:
            ProductImage.objects.create(
                product=product,
                image=image,
                sort_order=next_sort_order,
            )
            next_sort_order += 1


class ProductListView(ProductDashboardMixin, ListView):
    context_object_name = "products"
    paginate_by = 10
    template_name = "dashboard/products/list.html"
    sortable_fields = {
        "name": "name",
        "price": "current_price",
        "stock": "stock_quantity",
        "updated": "updated_at",
    }

    def get_queryset(self):
        queryset = Product.objects.select_related("category", "brand").prefetch_related("images")
        search = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()
        brand_id = self.request.GET.get("brand", "").strip()
        status = self.request.GET.get("status", "").strip()
        stock_status = self.request.GET.get("stock_status", "").strip()
        sort = self.request.GET.get("sort", "").strip()

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        if category_id.isdigit():
            queryset = queryset.filter(category_id=int(category_id))
        if brand_id.isdigit():
            queryset = queryset.filter(brand_id=int(brand_id))
        if status in Product.Status.values:
            queryset = queryset.filter(status=status)
        if stock_status == "not_tracked":
            queryset = queryset.filter(track_stock=False)
        elif stock_status == "out":
            queryset = queryset.filter(track_stock=True, stock_quantity=0)
        elif stock_status == "low":
            queryset = queryset.filter(
                track_stock=True,
                stock_quantity__gt=0,
                stock_quantity__lte=F("low_stock_threshold"),
            )
        elif stock_status == "in":
            queryset = queryset.filter(track_stock=True, stock_quantity__gt=F("low_stock_threshold"))

        sort_field = sort.lstrip("-")
        if sort_field in self.sortable_fields:
            ordering = f"{'-' if sort.startswith('-') else ''}{self.sortable_fields[sort_field]}"
        else:
            ordering = "-id"
        return queryset.order_by(ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", "").strip(),
            "category": self.request.GET.get("category", "").strip(),
            "brand": self.request.GET.get("brand", "").strip(),
            "status": self.request.GET.get("status", "").strip(),
            "stock_status": self.request.GET.get("stock_status", "").strip(),
        }
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        sort_query_params = query_params.copy()
        sort_query_params.pop("sort", None)
        current_sort = self.request.GET.get("sort", "").strip()
        sort_options = {}
        for key in self.sortable_fields:
            if current_sort == key:
                direction = "asc"
                next_sort = f"-{key}"
            elif current_sort == f"-{key}":
                direction = "desc"
                next_sort = key
            else:
                direction = ""
                next_sort = key
            sort_options[key] = {"direction": direction, "next": next_sort}
        context.update(
            {
                "categories": Category.objects.only("id", "name").order_by("name", "id"),
                "brands": Brand.objects.only("id", "name").order_by("name", "id"),
                "filters": filters,
                "pagination_query": query_params.urlencode(),
                "sort_query": sort_query_params.urlencode(),
                "sort_options": sort_options,
            }
        )
        return context


class ProductDetailView(ProductDashboardMixin, DetailView):
    context_object_name = "product"
    template_name = "dashboard/products/detail.html"

    def get_queryset(self):
        return Product.objects.select_related("category", "brand").prefetch_related(
            "images", "reviews", "stock_transactions__created_by"
        ).order_by("-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.name
        reviews = list(self.object.reviews.all())
        review_count = len(reviews)
        average_rating = round(sum(review.rating for review in reviews) / review_count, 1) if review_count else 0

        for review in reviews:
            review.full_stars = range(review.rating)
            review.empty_stars_range = range(max(5 - review.rating, 0))

        breakdown = []
        for rating in range(5, 0, -1):
            rating_total = sum(1 for review in reviews if review.rating == rating)
            percentage = round((rating_total / review_count) * 100) if review_count else 0
            breakdown.append(
                {
                    "rating": rating,
                    "count": rating_total,
                    "percentage": percentage,
                }
            )

        context["reviews"] = reviews
        context["review_summary"] = {
            "count": review_count,
            "average": average_rating,
            "breakdown": breakdown,
        }
        context["stock_transactions"] = list(self.object.stock_transactions.all()[:10])
        stock_totals = self.object.stock_transactions.aggregate(
            total_purchased=Coalesce(
                Sum("quantity_change", filter=Q(transaction_type=StockTransaction.TransactionType.PURCHASE)), 0
            ),
            total_sold_raw=Coalesce(
                Sum("quantity_change", filter=Q(transaction_type=StockTransaction.TransactionType.SALE)), 0
            ),
            total_returned=Coalesce(
                Sum(
                    "quantity_change",
                    filter=Q(transaction_type=StockTransaction.TransactionType.SALE_RETURN),
                ),
                0,
            ),
        )
        context["stock_totals"] = {
            "purchased": stock_totals["total_purchased"],
            "sold": abs(stock_totals["total_sold_raw"]),
            "returned": stock_totals["total_returned"],
        }
        return context


class ProductCreateView(ProductDashboardMixin, CreateView):
    template_name = "dashboard/products/form.html"
    permission_required = "category.add_product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Product"
        context["submit_label"] = "Save Product"
        return context

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            self.sync_images(self.object, form)
            opening_stock = self.object.stock_quantity
            if opening_stock:
                StockTransaction.objects.create(
                    product=self.object,
                    transaction_type=StockTransaction.TransactionType.OPENING_STOCK,
                    quantity_change=opening_stock,
                    balance_after=opening_stock,
                    reference="Product creation",
                    created_by=self.request.user if self.request.user.is_authenticated else None,
                )
        messages.success(
            self.request,
            "Product created successfully.",
            extra_tags="toast-create",
        )
        return response


class ProductUpdateView(ProductDashboardMixin, UpdateView):
    template_name = "dashboard/products/form.html"
    permission_required = "category.change_product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Product"
        context["submit_label"] = "Update Product"
        return context

    def form_valid(self, form):
        previous_quantity = Product.objects.filter(pk=form.instance.pk).values_list(
            "stock_quantity", flat=True
        ).get()
        new_quantity = form.cleaned_data["stock_quantity"]
        with transaction.atomic():
            response = super().form_valid(form)
            self.sync_images(self.object, form)
            quantity_change = new_quantity - previous_quantity
            if quantity_change:
                StockTransaction.objects.create(
                    product=self.object,
                    transaction_type=StockTransaction.TransactionType.MANUAL_ADJUSTMENT,
                    quantity_change=quantity_change,
                    balance_after=new_quantity,
                    reference="Dashboard product edit",
                    created_by=self.request.user if self.request.user.is_authenticated else None,
                )
        messages.info(
            self.request,
            "Product updated successfully.",
            extra_tags="toast-edit",
        )
        return response


class ProductDeleteView(DashboardPermissionMixin, View):
    permission_required = "category.delete_product"

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        deleted_names, blocked_products = delete_products_safely([product])
        if deleted_names:
            messages.error(
                request,
                f'"{deleted_names[0]}" deleted successfully.',
                extra_tags="toast-delete",
            )
        else:
            blocker_labels = ", ".join(blocked_products[0][1])
            messages.warning(
                request,
                f'"{product.name}" was not deleted because it has linked {blocker_labels}.',
                extra_tags="toast-warning",
            )
        return redirect("dashboard_product_list")


class ProductBulkActionView(DashboardPermissionMixin, View):
    permission_required = "category.view_product"
    status_actions = {
        "publish": Product.Status.PUBLISHED,
        "draft": Product.Status.DRAFT,
        "inactive": Product.Status.INACTIVE,
    }

    def post(self, request):
        action = request.POST.get("action", "").strip()
        selected_ids = {
            int(product_id)
            for product_id in request.POST.getlist("selected_products")
            if product_id.isdigit()
        }
        if not selected_ids:
            messages.error(request, "Select at least one product before applying an action.")
            return redirect("dashboard_product_list")

        products = Product.objects.filter(pk__in=selected_ids)
        if not products.exists():
            messages.error(request, "None of the selected products could be found.")
            return redirect("dashboard_product_list")
        if action in self.status_actions:
            if not request.user.has_perm("category.change_product"):
                messages.error(request, "You do not have permission to update products.")
                return redirect("dashboard_product_list")
            updated_count = products.update(status=self.status_actions[action], updated_at=timezone.now())
            messages.success(request, f"Updated {updated_count} product(s).", extra_tags="toast-edit")
        elif action == "delete":
            if not request.user.has_perm("category.delete_product"):
                messages.error(request, "You do not have permission to delete products.")
                return redirect("dashboard_product_list")
            products = products.prefetch_related(
                "stock_transactions",
                "order_items",
                "order_stock_applications",
                "sale_items",
                "purchase_items",
                "purchase_stock_applications",
            )
            deleted_names, blocked_products = delete_products_safely(products)
            if deleted_names:
                messages.error(
                    request,
                    f"Deleted {len(deleted_names)} product(s).",
                    extra_tags="toast-delete",
                )
            if blocked_products:
                messages.warning(
                    request,
                    f"{len(blocked_products)} product(s) were not deleted because they have linked records.",
                    extra_tags="toast-warning",
                )
        else:
            messages.error(request, "Choose a valid bulk action.")
        return redirect("dashboard_product_list")


class ProductDuplicateView(DashboardPermissionMixin, View):
    permission_required = "category.add_product"

    def post(self, request, pk):
        source = get_object_or_404(Product, pk=pk)
        name_prefix = "Copy of "
        duplicate_name = f"{name_prefix}{source.name}"[: Product._meta.get_field("name").max_length]
        with transaction.atomic():
            duplicate = Product.objects.create(
                category=source.category,
                brand=source.brand,
                name=duplicate_name,
                regular_price=source.regular_price,
                current_price=source.current_price,
                sku=Product.generate_unique_sku(),
                status=Product.Status.DRAFT,
                availability=source.availability if not source.track_stock else "",
                track_stock=source.track_stock,
                stock_quantity=0,
                low_stock_threshold=source.low_stock_threshold,
                short_description=source.short_description,
                full_description=source.full_description,
            )
        messages.success(
            request,
            f'"{source.name}" duplicated as a draft product.',
            extra_tags="toast-create",
        )
        return redirect("dashboard_product_edit", pk=duplicate.pk)


class InventoryDashboardMixin(DashboardPermissionMixin):
    permission_required = "category.view_product"

    def can_view_cost(self):
        return self.request.user.is_superuser or self.request.user.has_perm("purchase.view_purchase")


def inventory_products_queryset():
    latest_purchase_cost = PurchaseItem.objects.filter(product=OuterRef("pk")).order_by(
        "-purchase__purchase_date", "-id"
    ).values("unit_price")[:1]
    return Product.objects.select_related("category", "brand").annotate(
        latest_cost=Subquery(latest_purchase_cost),
        total_purchased=Coalesce(
            Sum("stock_transactions__quantity_change", filter=Q(stock_transactions__transaction_type=StockTransaction.TransactionType.PURCHASE)),
            0,
        ),
        total_sold_raw=Coalesce(
            Sum("stock_transactions__quantity_change", filter=Q(stock_transactions__transaction_type=StockTransaction.TransactionType.SALE)),
            0,
        ),
        total_returned=Coalesce(
            Sum("stock_transactions__quantity_change", filter=Q(stock_transactions__transaction_type=StockTransaction.TransactionType.SALE_RETURN)),
            0,
        ),
    )


class InventoryReportView(InventoryDashboardMixin, ListView):
    context_object_name = "products"
    paginate_by = 25
    template_name = "dashboard/inventory/report.html"

    def get_queryset(self):
        queryset = inventory_products_queryset().order_by("name", "id")
        search = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()
        stock_status = self.request.GET.get("stock_status", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        if category_id.isdigit():
            queryset = queryset.filter(category_id=int(category_id))
        if stock_status == "not_tracked":
            queryset = queryset.filter(track_stock=False)
        elif stock_status == "out":
            queryset = queryset.filter(track_stock=True, stock_quantity=0)
        elif stock_status == "low":
            queryset = queryset.filter(track_stock=True, stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold"))
        elif stock_status == "in":
            queryset = queryset.filter(track_stock=True, stock_quantity__gt=F("low_stock_threshold"))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Inventory Report"
        context["categories"] = Category.objects.order_by("name")
        context["filters"] = {
            "q": self.request.GET.get("q", "").strip(),
            "category": self.request.GET.get("category", "").strip(),
            "stock_status": self.request.GET.get("stock_status", "").strip(),
        }
        context["can_view_cost"] = self.can_view_cost()
        for product in context["products"]:
            product.total_sold = abs(product.total_sold_raw or 0)
            product.stock_value = product.stock_quantity * product.latest_cost if product.latest_cost is not None else None
        return context


class StockHistoryView(InventoryDashboardMixin, ListView):
    context_object_name = "transactions"
    paginate_by = 30
    template_name = "dashboard/inventory/history.html"

    def get_queryset(self):
        queryset = StockTransaction.objects.select_related("product", "product__category", "created_by")
        product_id = self.request.GET.get("product", "").strip()
        transaction_type = self.request.GET.get("transaction_type", "").strip()
        reference = self.request.GET.get("reference", "").strip()
        date_from = parse_date(self.request.GET.get("date_from", ""))
        date_to = parse_date(self.request.GET.get("date_to", ""))
        if product_id.isdigit():
            queryset = queryset.filter(product_id=int(product_id))
        if transaction_type in StockTransaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)
        if reference:
            queryset = queryset.filter(Q(reference__icontains=reference) | Q(note__icontains=reference))
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Stock History"
        context["products"] = Product.objects.order_by("name", "id").only("id", "name", "sku")
        context["transaction_types"] = StockTransaction.TransactionType.choices
        context["filters"] = {
            key: self.request.GET.get(key, "").strip()
            for key in ("product", "transaction_type", "reference", "date_from", "date_to")
        }
        return context
