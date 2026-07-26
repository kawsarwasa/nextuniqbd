from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from sitepages.permissions import DashboardPermissionMixin

from .forms import BlogCategoryForm, BlogCommentForm, BlogPostForm, BlogTagForm
from .models import BlogCategory, BlogComment, BlogPost, BlogPostImage, BlogTag


class BlogCategoryDashboardMixin(DashboardPermissionMixin):
    model = BlogCategory
    form_class = BlogCategoryForm
    success_url = reverse_lazy("dashboard_blog_category_list")
    permission_required = "blog.view_blogcategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["blog_category_total"] = BlogCategory.objects.count()
        context["blog_category_active_total"] = BlogCategory.objects.filter(is_active=True).count()
        return context


class BlogCategoryListView(BlogCategoryDashboardMixin, ListView):
    context_object_name = "categories"
    paginate_by = 10
    template_name = "dashboard/blog/categories/list.html"

    def get_queryset(self):
        return BlogCategory.objects.order_by("sort_order", "name", "id")


class BlogCategoryCreateView(BlogCategoryDashboardMixin, CreateView):
    template_name = "dashboard/blog/categories/form.html"
    permission_required = "blog.add_blogcategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Blog Category"
        context["submit_label"] = "Save Category"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Blog category created successfully.", extra_tags="toast-create")
        return response


class BlogCategoryUpdateView(BlogCategoryDashboardMixin, UpdateView):
    template_name = "dashboard/blog/categories/form.html"
    permission_required = "blog.change_blogcategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Blog Category"
        context["submit_label"] = "Update Category"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Blog category updated successfully.", extra_tags="toast-edit")
        return response


class BlogCategoryDeleteView(DashboardPermissionMixin, View):
    permission_required = "blog.delete_blogcategory"

    def post(self, request, pk):
        category = get_object_or_404(BlogCategory, pk=pk)
        category_name = category.name
        was_deleted = category.safe_delete()

        if was_deleted:
            messages.error(request, f'"{category_name}" deleted successfully.', extra_tags="toast-delete")
        else:
            messages.warning(
                request,
                f'"{category_name}" could not be deleted and was deactivated instead.',
                extra_tags="toast-warning",
            )

        return redirect("dashboard_blog_category_list")


class BlogTagDashboardMixin(DashboardPermissionMixin):
    model = BlogTag
    form_class = BlogTagForm
    success_url = reverse_lazy("dashboard_blog_tag_list")
    permission_required = "blog.view_blogtag"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["blog_tag_total"] = BlogTag.objects.count()
        context["blog_tag_active_total"] = BlogTag.objects.filter(is_active=True).count()
        return context


class BlogTagListView(BlogTagDashboardMixin, ListView):
    context_object_name = "tags"
    paginate_by = 10
    template_name = "dashboard/blog/tags/list.html"

    def get_queryset(self):
        return BlogTag.objects.order_by("name", "id")


class BlogTagCreateView(BlogTagDashboardMixin, CreateView):
    template_name = "dashboard/blog/tags/form.html"
    permission_required = "blog.add_blogtag"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Blog Tag"
        context["submit_label"] = "Save Tag"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Blog tag created successfully.", extra_tags="toast-create")
        return response


class BlogTagUpdateView(BlogTagDashboardMixin, UpdateView):
    template_name = "dashboard/blog/tags/form.html"
    permission_required = "blog.change_blogtag"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Blog Tag"
        context["submit_label"] = "Update Tag"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Blog tag updated successfully.", extra_tags="toast-edit")
        return response


class BlogTagDeleteView(DashboardPermissionMixin, View):
    permission_required = "blog.delete_blogtag"

    def post(self, request, pk):
        tag = get_object_or_404(BlogTag, pk=pk)
        tag_name = tag.name
        tag.safe_delete()
        messages.error(request, f'"{tag_name}" deleted successfully.', extra_tags="toast-delete")
        return redirect("dashboard_blog_tag_list")


class BlogPostDashboardMixin(DashboardPermissionMixin):
    model = BlogPost
    form_class = BlogPostForm
    success_url = reverse_lazy("dashboard_blog_post_list")
    permission_required = "blog.view_blogpost"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["blog_post_total"] = BlogPost.objects.count()
        context["blog_post_published_total"] = BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).count()
        context["blog_post_draft_total"] = BlogPost.objects.filter(status=BlogPost.Status.DRAFT).count()
        context["blog_comment_total"] = BlogComment.objects.count()
        return context

    def sync_images(self, post, form):
        remove_images = form.cleaned_data.get("remove_images") or []
        if remove_images:
            post.images.filter(pk__in=remove_images).delete()

        next_sort_order = post.images.order_by("-sort_order").values_list("sort_order", flat=True).first()
        next_sort_order = 0 if next_sort_order is None else next_sort_order + 1

        for image in form.cleaned_data.get("new_images") or []:
            BlogPostImage.objects.create(
                post=post,
                image=image,
                sort_order=next_sort_order,
            )
            next_sort_order += 1


class BlogPostListView(BlogPostDashboardMixin, ListView):
    context_object_name = "posts"
    paginate_by = 10
    template_name = "dashboard/blog/posts/list.html"

    def get_queryset(self):
        return (
            BlogPost.objects.select_related("category")
            .prefetch_related("tags", "images")
            .annotate(comment_count=Count("comments"))
            .order_by("-updated_at", "-id")
        )


class BlogPostDetailView(BlogPostDashboardMixin, DetailView):
    context_object_name = "post"
    template_name = "dashboard/blog/posts/detail.html"

    def get_queryset(self):
        return (
            BlogPost.objects.select_related("category")
            .prefetch_related("tags", "images", "comments")
            .order_by("-updated_at", "-id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        comments = list(self.object.comments.all())
        context["page_title"] = self.object.title
        context["approved_comment_total"] = sum(1 for comment in comments if comment.is_approved)
        context["pending_comment_total"] = sum(1 for comment in comments if not comment.is_approved)
        context["comments"] = comments
        return context


class BlogPostCreateView(BlogPostDashboardMixin, CreateView):
    template_name = "dashboard/blog/posts/form.html"
    permission_required = "blog.add_blogpost"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Blog Post"
        context["submit_label"] = "Save Post"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.sync_images(self.object, form)
        messages.success(self.request, "Blog post created successfully.", extra_tags="toast-create")
        return response


class BlogPostUpdateView(BlogPostDashboardMixin, UpdateView):
    template_name = "dashboard/blog/posts/form.html"
    permission_required = "blog.change_blogpost"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Blog Post"
        context["submit_label"] = "Update Post"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.sync_images(self.object, form)
        messages.info(self.request, "Blog post updated successfully.", extra_tags="toast-edit")
        return response


class BlogPostDeleteView(DashboardPermissionMixin, View):
    permission_required = "blog.delete_blogpost"

    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        post_title = post.title
        post.delete()
        messages.error(request, f'"{post_title}" deleted successfully.', extra_tags="toast-delete")
        return redirect("dashboard_blog_post_list")


class BlogCommentDashboardMixin(DashboardPermissionMixin):
    model = BlogComment
    form_class = BlogCommentForm
    success_url = reverse_lazy("dashboard_blog_comment_list")
    permission_required = "blog.view_blogcomment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["blog_comment_total"] = BlogComment.objects.count()
        context["blog_comment_approved_total"] = BlogComment.objects.filter(is_approved=True).count()
        context["blog_comment_pending_total"] = BlogComment.objects.filter(is_approved=False).count()
        return context


class BlogCommentListView(BlogCommentDashboardMixin, ListView):
    context_object_name = "comments"
    paginate_by = 10
    template_name = "dashboard/blog/comments/list.html"

    def get_queryset(self):
        return BlogComment.objects.select_related("post", "post__category").order_by("-created_at", "-id")


class BlogCommentCreateView(BlogCommentDashboardMixin, CreateView):
    template_name = "dashboard/blog/comments/form.html"
    permission_required = "blog.add_blogcomment"

    def get_initial(self):
        initial = super().get_initial()
        post_id = self.request.GET.get("post")
        if post_id and post_id.isdigit():
            initial["post"] = int(post_id)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Add Blog Comment"
        context["submit_label"] = "Save Comment"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Blog comment created successfully.", extra_tags="toast-create")
        return response


class BlogCommentUpdateView(BlogCommentDashboardMixin, UpdateView):
    template_name = "dashboard/blog/comments/form.html"
    permission_required = "blog.change_blogcomment"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Blog Comment"
        context["submit_label"] = "Update Comment"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.info(self.request, "Blog comment updated successfully.", extra_tags="toast-edit")
        return response


class BlogCommentDeleteView(DashboardPermissionMixin, View):
    permission_required = "blog.delete_blogcomment"

    def post(self, request, pk):
        comment = get_object_or_404(BlogComment, pk=pk)
        author_name = comment.author_name
        comment.delete()
        messages.error(request, f'Comment by "{author_name}" deleted successfully.', extra_tags="toast-delete")
        return redirect("dashboard_blog_comment_list")
