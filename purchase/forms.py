from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from category.models import Product

from .models import Purchase, PurchaseItem


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = [
            "supplier_name",
            "supplier_phone",
            "supplier_address",
        ]
        widgets = {
            "supplier_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional supplier name"}),
            "supplier_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional supplier phone"}),
            "supplier_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Optional supplier address"}
            ),
        }


class PurchaseItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select js-searchable-select purchase-product-select",
                "data-search-placeholder": "Search product",
            }
        ),
    )
    subtotal = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        disabled=True,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "readonly": True}),
    )

    class Meta:
        model = PurchaseItem
        fields = ["product", "quantity", "unit_price", "subtotal"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "1", "step": "1"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product_queryset = Product.objects.select_related("category", "brand").order_by("name", "id")
        self.fields["product"].queryset = product_queryset
        self.fields["product"].label_from_instance = self.build_product_label
        self.fields["quantity"].required = False
        self.fields["unit_price"].required = False
        if not self.instance.pk and not self.is_bound:
            self.fields["quantity"].initial = None
            self.fields["unit_price"].initial = None
        self.product_display_value = ""
        selected_product_id = self["product"].value()
        if selected_product_id:
            selected_product = product_queryset.filter(pk=selected_product_id).first()
            if selected_product is not None:
                self.product_display_value = self.build_product_label(selected_product)
        elif self.instance.pk and self.instance.product_id:
            self.product_display_value = self.build_product_label(self.instance.product)

    def has_changed(self):
        if self.is_bound and not self.instance.pk:
            raw_values = [
                (self.data.get(self.add_prefix("product")) or "").strip(),
                (self.data.get(self.add_prefix("quantity")) or "").strip(),
                (self.data.get(self.add_prefix("unit_price")) or "").strip(),
            ]
            if not any(raw_values):
                return False
        return super().has_changed()

    @staticmethod
    def build_product_label(product):
        parts = [product.name]
        if product.sku:
            parts.append(f"SKU: {product.sku}")
        if product.category_id:
            category_label = product.category.name
            if product.brand_id:
                category_label = f"{category_label} / {product.brand.name}"
            parts.append(category_label)
        return " | ".join(parts)


class BasePurchaseItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        valid_item_count = 0

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            quantity = form.cleaned_data.get("quantity")
            unit_price = form.cleaned_data.get("unit_price")

            if not product and not quantity and (unit_price in (None, "")):
                continue

            if not product:
                form.add_error("product", "Product is required.")
            if not quantity:
                form.add_error("quantity", "Quantity is required.")
            if unit_price is None:
                form.add_error("unit_price", "Unit price is required.")

            if product and quantity and unit_price is not None:
                valid_item_count += 1

        if valid_item_count == 0:
            raise forms.ValidationError("Add at least one purchase item.")


PurchaseItemFormSet = inlineformset_factory(
    Purchase,
    PurchaseItem,
    form=PurchaseItemForm,
    formset=BasePurchaseItemFormSet,
    extra=1,
    can_delete=True,
)


PurchaseItemEditFormSet = inlineformset_factory(
    Purchase,
    PurchaseItem,
    form=PurchaseItemForm,
    formset=BasePurchaseItemFormSet,
    extra=0,
    can_delete=True,
)
