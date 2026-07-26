from django import forms
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .models import BlogCategory, BlogComment, BlogPost, BlogTag


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        if not data:
            return []
        return [single_clean(data, initial)]


class BlogCategoryForm(forms.ModelForm):
    class Meta:
        model = BlogCategory
        fields = ["name", "description", "sort_order", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category name"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Short category description"}
            ),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BlogTagForm(forms.ModelForm):
    class Meta:
        model = BlogTag
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tag name"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Optional tag description"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BlogPostForm(forms.ModelForm):
    MAX_POST_IMAGES = 8
    MAX_IMAGE_PIXELS = 4_000_000

    new_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control", "multiple": True, "accept": "image/*"}),
    )
    remove_images = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    content_html = forms.CharField(widget=forms.HiddenInput(), required=False)
    published_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = BlogPost
        fields = [
            "category",
            "tags",
            "title",
            "author_name",
            "excerpt",
            "content_html",
            "featured_image",
            "status",
            "allow_comments",
            "published_at",
        ]
        widgets = {
            "category": forms.Select(
                attrs={
                    "class": "form-select js-searchable-select",
                    "data-search-placeholder": "Search category",
                }
            ),
            "tags": forms.CheckboxSelectMultiple(),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Blog post title"}),
            "author_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Author name"}),
            "excerpt": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Short summary for blog cards or SEO"}
            ),
            "featured_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "allow_comments": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = BlogCategory.objects.filter(is_active=True).order_by("name")
        self.fields["tags"].queryset = BlogTag.objects.filter(is_active=True).order_by("name")
        self.fields["new_images"].help_text = (
            f"You can attach up to {self.MAX_POST_IMAGES} gallery images. "
            "Each image must be 4 megapixels or smaller; for square photos, use 2000 x 2000 px or smaller."
        )
        self.fields["featured_image"].help_text = "Recommended size: 1200 x 630 px."

        if self.instance.pk:
            self.fields["content_html"].initial = self.instance.content
            self.fields["remove_images"].choices = [
                (str(image.pk), image.image.name.split("/")[-1]) for image in self.instance.images.all()
            ]
            if self.instance.published_at:
                local_published_at = timezone.localtime(self.instance.published_at)
                self.initial["published_at"] = local_published_at.strftime("%Y-%m-%dT%H:%M")
        else:
            self.fields["content_html"].initial = ""
            self.fields["remove_images"].choices = []
            self.initial.setdefault("author_name", "Dashboard User")

    def clean_remove_images(self):
        selected_ids = self.cleaned_data.get("remove_images") or []
        valid_ids = {str(image.pk) for image in self.instance.images.all()} if self.instance.pk else set()
        return [image_id for image_id in selected_ids if image_id in valid_ids]

    def clean_new_images(self):
        files = self.cleaned_data.get("new_images") or []
        errors = []

        for file in files:
            try:
                if hasattr(file, "seek"):
                    file.seek(0)

                with Image.open(file) as image:
                    width, height = image.size

                if width * height > self.MAX_IMAGE_PIXELS:
                    errors.append(
                        f"{file.name}: image exceeds the 4 megapixel limit. "
                        "For square photos, resize to 2000 x 2000 px or smaller."
                    )
            except (UnidentifiedImageError, OSError):
                errors.append(f"{file.name}: invalid image file.")
            finally:
                if hasattr(file, "seek"):
                    file.seek(0)

        if errors:
            raise forms.ValidationError(errors)

        return files

    def clean(self):
        cleaned_data = super().clean()
        existing_image_total = self.instance.images.count() if self.instance.pk else 0
        removed_image_total = len(cleaned_data.get("remove_images") or [])
        kept_existing_total = max(existing_image_total - removed_image_total, 0)
        new_image_total = len(cleaned_data.get("new_images") or [])

        if kept_existing_total + new_image_total > self.MAX_POST_IMAGES:
            self.add_error(
                "new_images",
                f"You can keep up to {self.MAX_POST_IMAGES} gallery images per post.",
            )

        published_at = cleaned_data.get("published_at")
        if cleaned_data.get("status") == BlogPost.Status.PUBLISHED and not published_at:
            cleaned_data["published_at"] = timezone.now()

        cleaned_data["content"] = cleaned_data.get("content_html", "")
        return cleaned_data

    def save(self, commit=True):
        post = super().save(commit=False)
        post.content = self.cleaned_data.get("content", "")
        if commit:
            post.save()
            self.save_m2m()
        return post


class BlogCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ["post", "author_name", "author_email", "body", "is_approved"]
        widgets = {
            "post": forms.Select(
                attrs={
                    "class": "form-select js-searchable-select",
                    "data-search-placeholder": "Search post",
                }
            ),
            "author_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Comment author"}),
            "author_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}),
            "body": forms.Textarea(
                attrs={"class": "form-control", "rows": 6, "placeholder": "Comment body"}
            ),
            "is_approved": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["post"].queryset = BlogPost.objects.select_related("category").order_by("-created_at")
        self.fields["post"].label_from_instance = lambda post: f"{post.title} ({post.category.name})"
