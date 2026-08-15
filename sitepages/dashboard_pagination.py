"""Shared pagination helpers for dashboard list and table views."""

from django.core.paginator import Paginator


DEFAULT_DASHBOARD_PAGE_SIZE = 20


def build_dashboard_pagination_context(request, page_obj):
    """Keep all non-page query parameters and render a compact page range."""
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return {
        "pagination_query": query_params.urlencode(),
        "pagination_page_numbers": page_obj.paginator.get_elided_page_range(
            page_obj.number,
            on_each_side=1,
            on_ends=1,
        ),
    }


class DashboardPaginationContextMixin:
    """Provide shared pagination context to dashboard class-based list views."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_obj = context.get("page_obj")
        if page_obj is not None:
            context.update(build_dashboard_pagination_context(self.request, page_obj))
        return context

    def paginate_queryset(self, queryset, page_size):
        """Use Django's forgiving paginator for invalid dashboard page values."""
        paginator = Paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_obj = paginator.get_page(self.request.GET.get(self.page_kwarg))
        return paginator, page_obj, page_obj.object_list, page_obj.has_other_pages()
