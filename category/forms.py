from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Brand, Category, Product, ProductImage


class CategoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].help_text = (
            "Recommended size: 600 x 600 px. Uploaded category images are resized to this size."
        )

    class Meta:
        model = Category
        fields = [
            "name",
            "short_description",
            "icon_class",
            "image",
            "sort_order",
            "is_active",
            "show_on_homepage",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Enter category name"}
            ),
            "short_description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Short summary for listings"}
            ),
            "icon_class": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "fa fa-tag"}
            ),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_on_homepage": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BrandForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logo"].help_text = "Recommended size: 600 x 600 px."

    class Meta:
        model = Brand
        fields = [
            "name",
            "description",
            "logo",
            "is_active",
            "show_on_homepage",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Enter brand name"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Write a short brand description",
                }
            ),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_on_homepage": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


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


class ProductForm(forms.ModelForm):
    MAX_PRODUCT_IMAGES = 4
    MAX_IMAGE_PIXELS = 2_000_000
    MAX_PRODUCT_IMAGE_BYTES = 3 * 1024 * 1024
    MAX_PRODUCT_IMAGE_SIZE_LABEL = "3 MB"
    AVAILABILITY_IN_STOCK = "In Stock"
    AVAILABILITY_OUT_OF_STOCK = "Out of Stock"
    AVAILABILITY_CHOICES = (
        (AVAILABILITY_IN_STOCK, AVAILABILITY_IN_STOCK),
        (AVAILABILITY_OUT_OF_STOCK, AVAILABILITY_OUT_OF_STOCK),
    )

    new_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control", "multiple": True}),
    )
    remove_images = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    full_description_html = forms.CharField(required=False, widget=forms.HiddenInput())
    availability = forms.ChoiceField(
        choices=AVAILABILITY_CHOICES,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "regular_price",
            "current_price",
            "sku",
            "brand",
            "status",
            "is_featured",
            "availability",
            "track_stock",
            "stock_quantity",
            "low_stock_threshold",
            "short_description",
            "full_description_html",
        ]
        widgets = {
            "category": forms.Select(
                attrs={
                    "class": "form-select js-searchable-select",
                    "data-search-placeholder": "Search category",
                }
            ),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Product name"}),
            "regular_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "current_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sku": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ab#29x",
                    "autocomplete": "off",
                    "maxlength": Product.SKU_LENGTH,
                }
            ),
            "brand": forms.Select(
                attrs={
                    "class": "form-select js-searchable-select",
                    "data-search-placeholder": "Search brand",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "is_featured": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "track_stock": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "stock_quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "low_stock_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "short_description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Short product summary"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brand"].required = False
        self.fields["sku"].required = True
        self.fields["sku"].widget.attrs["maxlength"] = Product.SKU_LENGTH
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["brand"].queryset = Brand.objects.order_by("name")
        self.fields["new_images"].help_text = (
            f"You can add up to {self.MAX_PRODUCT_IMAGES} product images. "
            f"Each image must be {self.MAX_PRODUCT_IMAGE_SIZE_LABEL} or smaller and 2 megapixels or smaller; "
            "for square photos, use 1400 x 1400 px or smaller."
        )
        self.fields["new_images"].widget.attrs.update(
            {
                "accept": "image/*",
                "data-max-file-size": self.MAX_PRODUCT_IMAGE_BYTES,
                "data-max-file-size-label": self.MAX_PRODUCT_IMAGE_SIZE_LABEL,
            }
        )

        if self.instance.pk:
            self.fields["full_description_html"].initial = self.instance.full_description
            self.fields["availability"].initial = self.normalize_availability(self.instance.availability)
            self.fields["remove_images"].choices = [
                (str(image.pk), image.image.name.split("/")[-1])
                for image in self.instance.images.all()
            ]
        else:
            self.fields["full_description_html"].initial = ""
            self.fields["status"].initial = Product.Status.PUBLISHED
            self.fields["availability"].initial = self.AVAILABILITY_IN_STOCK
            self.fields["remove_images"].choices = []

    @classmethod
    def normalize_availability(cls, value):
        normalized_value = (value or "").strip().lower()
        if "out" in normalized_value:
            return cls.AVAILABILITY_OUT_OF_STOCK
        return cls.AVAILABILITY_IN_STOCK

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()

        # An unchanged legacy SKU is valid for editing purposes only. Any new
        # or changed value must follow the current 12-character rule.
        if self.instance.pk and sku == self.instance.sku:
            return sku

        if len(sku) > Product.SKU_LENGTH:
            raise forms.ValidationError("SKU cannot be more than 12 characters.")
        if not all(character in Product.SKU_ALLOWED_CHARACTERS for character in sku):
            raise forms.ValidationError(
                "SKU can contain letters, numbers, and symbols, but not whitespace."
            )

        queryset = Product.objects.filter(sku=sku)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("A product with this SKU already exists.")

        return sku

    def clean_availability(self):
        return self.normalize_availability(self.cleaned_data.get("availability"))

    def clean_remove_images(self):
        selected_ids = self.cleaned_data.get("remove_images") or []
        valid_ids = {str(image.pk) for image in self.instance.images.all()} if self.instance.pk else set()
        return [image_id for image_id in selected_ids if image_id in valid_ids]

    def clean_new_images(self):
        files = self.cleaned_data.get("new_images") or []
        errors = []

        for file in files:
            try:
                if file.size > self.MAX_PRODUCT_IMAGE_BYTES:
                    errors.append(
                        f"{file.name}: file exceeds the maximum size of "
                        f"{self.MAX_PRODUCT_IMAGE_SIZE_LABEL}."
                    )
                    continue

                if hasattr(file, "seek"):
                    file.seek(0)

                with Image.open(file) as image:
                    width, height = image.size
                    image.verify()

                if width * height > self.MAX_IMAGE_PIXELS:
                    errors.append(
                        f"{file.name}: image exceeds the 2 megapixel limit. "
                        "For square photos, resize to 1400 x 1400 px or smaller."
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
        regular_price = cleaned_data.get("regular_price")
        current_price = cleaned_data.get("current_price")
        if regular_price is not None and current_price is not None and current_price > regular_price:
            self.add_error("current_price", "Current price cannot be greater than regular price.")

        existing_image_total = self.instance.images.count() if self.instance.pk else 0
        removed_image_total = len(cleaned_data.get("remove_images") or [])
        kept_existing_total = max(existing_image_total - removed_image_total, 0)
        new_image_total = len(cleaned_data.get("new_images") or [])

        if kept_existing_total + new_image_total > self.MAX_PRODUCT_IMAGES:
            self.add_error(
                "new_images",
                f"You can keep up to {self.MAX_PRODUCT_IMAGES} images per product.",
            )

        cleaned_data["full_description"] = cleaned_data.get("full_description_html", "")
        return cleaned_data

    def save(self, commit=True):
        product = super().save(commit=False)
        product.full_description = self.cleaned_data.get("full_description", "")
        if commit:
            product.save()
            self.save_m2m()
        return product
