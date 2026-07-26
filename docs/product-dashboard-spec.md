# Product Dashboard And Variant Architecture

This specification is aligned with the current Django project layout:

- `catalog` already owns `Category`, `SubCategory`, `Brand`, `Attribute`, and `AttributeValue`
- the storefront product page currently renders title, badges, rating, price, meta rows, gallery, selectors, quantity, and CTA actions from `templates/frontend/partials/product_detail/main.html`
- the project does not currently include DRF in `requirements.txt`, so serializer examples below assume `djangorestframework` will be added when the API layer is implemented

## 1. Product Form Field Structure

### Basic Info

Core identity and merchandising fields:

- `product_name`: required string, max 255
- `slug`: required unique slug, auto-generated from product name but editable
- `product_type`: required choice
  - `simple`
  - `variable`
- `category`: required FK to `Category`
- `subcategory`: nullable FK to `SubCategory`
- `brand`: nullable FK to `Brand`
- `vendor_display_name`: optional string for storefront vendor label in a single-vendor store
- `sku`: required unique 12-character base SKU, auto-generated as `NUB` plus 9 uppercase letters or digits
- `barcode`: optional unique barcode/GTIN
- `short_description`: required short marketing summary for the hero area
- `full_description`: long rich description for the description tab
- `tags_badges`: JSON list of badge objects
  - example: `[{ "label": "NEW", "style": "success" }, { "label": "-30%", "style": "sale" }]`
- `condition`: choice
  - `new`
  - `used`
  - `refurbished`
- `size_guide_url`: optional URL
- `rating_average`: decimal(3,2), denormalized display field or review aggregate
- `review_count`: positive integer, denormalized display field or review aggregate
- `is_active`: boolean
- `is_featured`: boolean

### Pricing

- `base_price`: required decimal(12,2)
- `compare_price`: optional decimal(12,2)
- `cost_price`: optional decimal(12,2)
- `discount_type`: choice
  - `none`
  - `percent`
  - `fixed`
- `discount_value`: decimal(12,2), default `0`
- `tax_class`: optional choice/string, for example `standard`, `reduced`, `zero`
- `price_includes_tax`: boolean

Derived display fields:

- `current_price`
- `discount_amount`
- `discount_percent`
- `discount_label`

### Media

- `featured_image`: single image
- `featured_image_alt`: optional string
- `gallery_images`: repeatable rows
  - `image`
  - `alt_text`
  - `sort_order`
  - `is_featured`
- `variant_image_support`: each variant may have one primary image plus optional extra images

### Inventory

- `track_inventory`: boolean
- `stock_scope`: choice
  - `product`
  - `variant`
- `stock_qty`: integer, used for simple products or non-variant stock
- `reserved_qty`: integer, readonly/calculated from open orders
- `low_stock_threshold`: integer
- `allow_backorder`: boolean
- `stock_status`: choice
  - `in_stock`
  - `out_of_stock`
  - `preorder`
  - `backorder`
  - `discontinued`
- `availability_label`: storefront string such as `In Stock`, `Only 3 Left`, `Preorder`

### Specifications

Display-only facts for the product detail page:

- `brand`
- `condition`
- `weight`
- `material`
- `warranty`
- `country_of_origin`
- unlimited custom rows:
  - `spec_key`
  - `spec_value`
  - `sort_order`

### Dynamic Attributes

Reusable configurable product options:

- `attribute_name`
- `attribute_slug`
- `attribute_type`
  - `text`
  - `color`
  - `number`
  - `size`
  - `select`
- `used_for_variants`: boolean
- `used_for_filters`: boolean
- `display_on_product_page`: boolean
- `values`: list of selectable values
- `allow_custom_values`: boolean for dashboard-level creation flow

Examples:

- Fashion: `Color`, `Size`
- Grocery: `Weight`
- Electronics: `RAM`, `Storage`, `Color`
- Cosmetics: `Shade`, `Volume`

### Variants

Each generated combination becomes a sellable child SKU.

Variant fields:

- `variant_key`: deterministic combination fingerprint
- `variant_name`: optional generated label such as `Black / M`
- `variant_sku`: required unique
- `variant_barcode`: optional unique
- `variant_price`: optional override, fallback to product base price
- `variant_compare_price`: optional override
- `variant_cost_price`: optional override
- `variant_image`: optional primary image
- `stock_qty`
- `reserved_qty`
- `low_stock_threshold`
- `allow_backorder`
- `stock_status`
- `availability_label`
- `weight_override`: optional
- `is_default`
- `is_active`
- `sort_order`

### SEO

- `meta_title`
- `meta_description`
- `canonical_url`
- `og_title`
- `og_description`
- `og_image`
- `schema_type`

## 2. Product Detail Page Mapping

Mapping from dashboard data to the current storefront layout:

- `product_name` -> hero title
- `tags_badges` -> inline badges above the title
- `rating_average` -> star rating block
- `review_count` -> reviews count and review tab label
- `brand.name` or `vendor_display_name` -> vendor / brand row
- `base_price` or variant effective price -> current price
- `compare_price` or variant compare price -> old price
- `discount_label` -> save badge
- `sku` or selected variant SKU -> SKU row
- `brand.name` -> Brand meta row
- `condition` -> Condition meta row
- specification key `Weight` -> Weight meta row
- `availability_label` -> Availability row
- `short_description` -> summary paragraph under meta
- `featured_image` + `gallery_images` -> gallery thumbnails and zoom image
- attributes with `attribute_type=color` -> color swatches
- attributes with `attribute_type=size` or `select` -> size/option selectors
- `size_guide_url` -> size guide link
- selected variant inventory -> quantity max and CTA availability
- `full_description` -> description tab
- custom specifications -> specification table in tabs area

## 3. Normalized Django Model Design

Recommended implementation for `catalog/models.py`. Existing `Category`, `SubCategory`, `Brand`, `Attribute`, and `AttributeValue` should be extended instead of duplicated.

```python
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.template.defaultfilters import slugify


class Product(models.Model):
    PRODUCT_TYPE_SIMPLE = "simple"
    PRODUCT_TYPE_VARIABLE = "variable"
    PRODUCT_TYPE_CHOICES = [
        (PRODUCT_TYPE_SIMPLE, "Simple"),
        (PRODUCT_TYPE_VARIABLE, "Variable"),
    ]

    CONDITION_NEW = "new"
    CONDITION_USED = "used"
    CONDITION_REFURBISHED = "refurbished"
    CONDITION_CHOICES = [
        (CONDITION_NEW, "New"),
        (CONDITION_USED, "Used"),
        (CONDITION_REFURBISHED, "Refurbished"),
    ]

    DISCOUNT_NONE = "none"
    DISCOUNT_PERCENT = "percent"
    DISCOUNT_FIXED = "fixed"
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_NONE, "No Discount"),
        (DISCOUNT_PERCENT, "Percent"),
        (DISCOUNT_FIXED, "Fixed Amount"),
    ]

    STOCK_SCOPE_PRODUCT = "product"
    STOCK_SCOPE_VARIANT = "variant"
    STOCK_SCOPE_CHOICES = [
        (STOCK_SCOPE_PRODUCT, "Product Level"),
        (STOCK_SCOPE_VARIANT, "Variant Level"),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=275, unique=True)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES)
    category = models.ForeignKey("catalog.Category", on_delete=models.PROTECT, related_name="products")
    subcategory = models.ForeignKey(
        "catalog.SubCategory",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    vendor_display_name = models.CharField(max_length=150, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=64, unique=True, null=True, blank=True)
    short_description = models.TextField()
    full_description = models.TextField(blank=True)
    tags_badges = models.JSONField(default=list, blank=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default=CONDITION_NEW)
    size_guide_url = models.URLField(blank=True)
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    review_count = models.PositiveIntegerField(default=0)
    base_price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default=DISCOUNT_NONE)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_class = models.CharField(max_length=50, blank=True)
    price_includes_tax = models.BooleanField(default=False)
    featured_image = models.ImageField(upload_to="products/featured/", blank=True, null=True)
    featured_image_alt = models.CharField(max_length=255, blank=True)
    track_inventory = models.BooleanField(default=True)
    stock_scope = models.CharField(max_length=20, choices=STOCK_SCOPE_CHOICES, default=STOCK_SCOPE_PRODUCT)
    availability_label = models.CharField(max_length=100, blank=True)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(blank=True)
    og_title = models.CharField(max_length=255, blank=True)
    og_description = models.CharField(max_length=320, blank=True)
    og_image = models.ImageField(upload_to="products/seo/", blank=True, null=True)
    schema_type = models.CharField(max_length=50, default="Product")
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        if self.discount_type == self.DISCOUNT_PERCENT and self.discount_value:
            return max(self.base_price - (self.base_price * self.discount_value / Decimal("100")), Decimal("0.00"))
        if self.discount_type == self.DISCOUNT_FIXED and self.discount_value:
            return max(self.base_price - self.discount_value, Decimal("0.00"))
        return self.base_price

    def clean(self):
        if self.compare_price is not None and self.compare_price < self.base_price:
            raise ValidationError({"compare_price": "Compare price must be greater than or equal to base price."})
        if self.product_type == self.PRODUCT_TYPE_VARIABLE and self.stock_scope != self.STOCK_SCOPE_VARIANT:
            raise ValidationError({"stock_scope": "Variable products should use variant-level inventory."})


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        related_name="images",
        null=True,
        blank=True,
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def clean(self):
        if self.variant and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "Variant must belong to the same product."})


class ProductSpecification(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specifications")
    key = models.CharField(max_length=120)
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "key"], name="catalog_product_spec_unique_key")
        ]


class ProductAttribute(models.Model):
    ATTRIBUTE_TYPE_CHOICES = [
        ("text", "Text"),
        ("color", "Color"),
        ("number", "Number"),
        ("size", "Size"),
        ("select", "Select"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="product_attributes")
    attribute = models.ForeignKey("catalog.Attribute", on_delete=models.PROTECT, related_name="product_links")
    attribute_type = models.CharField(max_length=20, choices=ATTRIBUTE_TYPE_CHOICES, default="select")
    used_for_variants = models.BooleanField(default=True)
    used_for_filters = models.BooleanField(default=True)
    display_on_product_page = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "attribute"], name="catalog_product_attribute_unique")
        ]


class ProductAttributeValue(models.Model):
    product_attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="allowed_values")
    attribute_value = models.ForeignKey("catalog.AttributeValue", on_delete=models.PROTECT, related_name="product_links")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_attribute", "attribute_value"],
                name="catalog_product_attribute_value_unique",
            )
        ]

    def clean(self):
        if self.attribute_value.attribute_id != self.product_attribute.attribute_id:
            raise ValidationError({"attribute_value": "Attribute value does not belong to the selected attribute."})
```

Continue the variant and inventory models:

```python
class ProductVariant(models.Model):
    STOCK_STATUS_IN_STOCK = "in_stock"
    STOCK_STATUS_OUT_OF_STOCK = "out_of_stock"
    STOCK_STATUS_PREORDER = "preorder"
    STOCK_STATUS_BACKORDER = "backorder"
    STOCK_STATUS_DISCONTINUED = "discontinued"
    STOCK_STATUS_CHOICES = [
        (STOCK_STATUS_IN_STOCK, "In Stock"),
        (STOCK_STATUS_OUT_OF_STOCK, "Out Of Stock"),
        (STOCK_STATUS_PREORDER, "Preorder"),
        (STOCK_STATUS_BACKORDER, "Backorder"),
        (STOCK_STATUS_DISCONTINUED, "Discontinued"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    combination_key = models.CharField(max_length=255)
    name = models.CharField(max_length=255, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=64, unique=True, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    compare_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True)
    availability_label = models.CharField(max_length=100, blank=True)
    weight_override = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "combination_key"], name="catalog_variant_unique_combination"),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_default=True),
                name="catalog_variant_single_default_per_product",
            ),
        ]

    def clean(self):
        if self.compare_price is not None:
            reference_price = self.price if self.price is not None else self.product.base_price
            if self.compare_price < reference_price:
                raise ValidationError({"compare_price": "Variant compare price must be >= effective selling price."})

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.effective_price


class ProductVariantAttributeValue(models.Model):
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="attribute_values")
    product_attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="variant_values")
    attribute_value = models.ForeignKey("catalog.AttributeValue", on_delete=models.PROTECT, related_name="variant_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["variant", "product_attribute"], name="catalog_variant_attr_unique"),
            models.UniqueConstraint(fields=["variant", "attribute_value"], name="catalog_variant_value_unique"),
        ]

    def clean(self):
        if self.product_attribute.product_id != self.variant.product_id:
            raise ValidationError({"product_attribute": "Product attribute must belong to the same product."})
        if self.attribute_value.attribute_id != self.product_attribute.attribute_id:
            raise ValidationError({"attribute_value": "Attribute value does not belong to the selected attribute."})


class Inventory(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory",
        null=True,
        blank=True,
    )
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="inventory",
        null=True,
        blank=True,
    )
    track_inventory = models.BooleanField(default=True)
    stock_qty = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_qty = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    low_stock_threshold = models.PositiveIntegerField(default=0)
    allow_backorder = models.BooleanField(default=False)
    stock_status = models.CharField(
        max_length=20,
        choices=ProductVariant.STOCK_STATUS_CHOICES,
        default=ProductVariant.STOCK_STATUS_IN_STOCK,
    )
    availability_label = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(product__isnull=False) & Q(variant__isnull=True))
                    | (Q(product__isnull=True) & Q(variant__isnull=False))
                ),
                name="catalog_inventory_exactly_one_owner",
            )
        ]

    @property
    def available_qty(self):
        return max(self.stock_qty - self.reserved_qty, 0)
```

### Notes On Existing Models

- keep the existing `Category`, `SubCategory`, and `Brand` tables
- extend the existing `Attribute` model with these optional fields:
  - `attribute_type`
  - `is_variant_axis`
  - `is_filterable`
  - `sort_order`
- extend the existing `AttributeValue` model with display metadata when needed:
  - `color_hex`
  - `swatch_image`
  - `display_value`
  - `sort_order`

## 4. Backend Data Flow

### Save Flow

1. Save `Product` basic info, pricing, inventory mode, and SEO.
2. Save primary media and gallery images.
3. Save specifications as repeatable `ProductSpecification` rows.
4. Save selected attributes into `ProductAttribute`.
5. Save allowed values into `ProductAttributeValue`.
6. If `product_type = variable`, generate combination candidates from all `ProductAttribute` rows where `used_for_variants = true`.
7. Build a deterministic `combination_key` from sorted attribute value IDs, for example `12-34-98`.
8. Upsert `ProductVariant` rows by `product + combination_key`.
9. Save selected values for each variant into `ProductVariantAttributeValue`.
10. Save `Inventory` per product or per variant depending on `stock_scope`.
11. Recalculate derived fields:
   - effective price
   - discount label
   - availability label
   - default variant

### Variant Generation Rules

- use Cartesian product only across attributes marked `used_for_variants=true`
- preserve manual edits on existing variants during regeneration
- never create duplicate `combination_key` values
- if a previously generated combination no longer exists, mark that variant inactive instead of deleting it if there is order history
- simple products should have no child variants

### Service Layer Recommendation

Use a dedicated service module instead of pushing variant logic into forms or views.

Suggested service functions:

- `save_product_draft(payload, files, user)`
- `sync_product_media(product, image_payloads)`
- `sync_product_specifications(product, specs_payloads)`
- `sync_product_attributes(product, attribute_payloads)`
- `generate_variant_matrix(product)`
- `sync_variant_inventory(variant, inventory_payload)`
- `build_product_detail_payload(product, selected_variant=None)`

## 5. Serializer And API Structure

Recommended serializer layout if DRF is added:

```python
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "sort_order", "is_featured"]


class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ["key", "value", "sort_order"]


class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeValue
        fields = ["id", "value", "slug"]


class ProductAttributeSerializer(serializers.ModelSerializer):
    attribute = serializers.StringRelatedField()
    values = serializers.SerializerMethodField()

    class Meta:
        model = ProductAttribute
        fields = [
            "id",
            "attribute",
            "attribute_type",
            "used_for_variants",
            "display_on_product_page",
            "values",
        ]


class InventorySerializer(serializers.ModelSerializer):
    available_qty = serializers.IntegerField(read_only=True)

    class Meta:
        model = Inventory
        fields = [
            "track_inventory",
            "stock_qty",
            "reserved_qty",
            "available_qty",
            "low_stock_threshold",
            "allow_backorder",
            "stock_status",
            "availability_label",
        ]


class ProductVariantSerializer(serializers.ModelSerializer):
    inventory = InventorySerializer(read_only=True)
    attributes = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "name",
            "sku",
            "price",
            "compare_price",
            "image",
            "availability_label",
            "is_default",
            "is_active",
            "attributes",
            "inventory",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, source="product_attributes", read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    inventory = InventorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "product_type",
            "short_description",
            "full_description",
            "tags_badges",
            "rating_average",
            "review_count",
            "base_price",
            "compare_price",
            "effective_price",
            "size_guide_url",
            "brand",
            "vendor_display_name",
            "sku",
            "condition",
            "availability_label",
            "featured_image",
            "featured_image_alt",
            "images",
            "inventory",
            "specifications",
            "attributes",
            "variants",
        ]
```

### Sample Product Detail JSON

```json
{
  "id": 101,
  "name": "EcoSmart Fleece Hoodie",
  "slug": "ecosmart-fleece-hoodie",
  "product_type": "variable",
  "category": {
    "id": 4,
    "name": "Fashion",
    "slug": "fashion"
  },
  "subcategory": {
    "id": 11,
    "name": "Hoodies",
    "slug": "hoodies"
  },
  "brand": {
    "id": 3,
    "name": "Common Good",
    "slug": "common-good"
  },
  "vendor_display_name": "Common Good",
  "sku": "SPORT-6-FS",
  "barcode": "8901234567890",
  "tags_badges": [
    { "label": "COMMON GOOD", "style": "brand" },
    { "label": "NEW", "style": "success" },
    { "label": "-30%", "style": "sale" }
  ],
  "rating_average": "4.50",
  "review_count": 24,
  "base_price": "245.00",
  "compare_price": "350.00",
  "effective_price": "245.00",
  "discount_label": "Save $105.00 (30%)",
  "condition": "new",
  "short_description": "Premium quality fleece hoodie made from sustainable materials for all-day comfort.",
  "full_description": "<p>The EcoSmart Fleece Hoodie is the perfect blend of comfort, style, and sustainability.</p>",
  "size_guide_url": "/size-guide/hoodies/",
  "featured_image": "/media/products/featured/ecosmart-main.jpg",
  "featured_image_alt": "EcoSmart Fleece Hoodie front view",
  "images": [
    {
      "id": 1,
      "image": "/media/products/gallery/ecosmart-main.jpg",
      "alt_text": "Front view",
      "sort_order": 1,
      "is_featured": true
    },
    {
      "id": 2,
      "image": "/media/products/gallery/ecosmart-side.jpg",
      "alt_text": "Side view",
      "sort_order": 2,
      "is_featured": false
    }
  ],
  "inventory": null,
  "availability_label": "In Stock",
  "specifications": [
    { "key": "Material", "value": "80% Recycled Polyester, 20% Cotton", "sort_order": 1 },
    { "key": "Weight", "value": "1.00 KGS", "sort_order": 2 },
    { "key": "Country of Origin", "value": "Portugal", "sort_order": 3 }
  ],
  "attributes": [
    {
      "id": 21,
      "name": "Color",
      "attribute_type": "color",
      "used_for_variants": true,
      "display_on_product_page": true,
      "values": [
        { "id": 301, "value": "Charcoal", "slug": "charcoal", "meta": { "hex": "#4a4a4a" } },
        { "id": 302, "value": "Navy Blue", "slug": "navy-blue", "meta": { "hex": "#1a3a6b" } }
      ]
    },
    {
      "id": 22,
      "name": "Size",
      "attribute_type": "size",
      "used_for_variants": true,
      "display_on_product_page": true,
      "values": [
        { "id": 401, "value": "S", "slug": "s" },
        { "id": 402, "value": "M", "slug": "m" },
        { "id": 403, "value": "L", "slug": "l" }
      ]
    }
  ],
  "variants": [
    {
      "id": 9001,
      "name": "Charcoal / M",
      "sku": "SPORT-6-FS-CHA-M",
      "price": "245.00",
      "compare_price": "350.00",
      "image": "/media/products/variants/charcoal-m.jpg",
      "availability_label": "In Stock",
      "is_default": true,
      "is_active": true,
      "attributes": [
        { "attribute": "Color", "value": "Charcoal" },
        { "attribute": "Size", "value": "M" }
      ],
      "inventory": {
        "track_inventory": true,
        "stock_qty": 12,
        "reserved_qty": 2,
        "available_qty": 10,
        "low_stock_threshold": 3,
        "allow_backorder": false,
        "stock_status": "in_stock",
        "availability_label": "In Stock"
      }
    }
  ]
}
```

## 6. Validation Rules

- `product_name` is required
- `slug` must be unique
- `base_price` is required and must be `>= 0`
- `compare_price >= effective selling price`
- `sku` must be unique at product level and match `^NUB[A-Z0-9]{9}$`
- `variant_sku` must be unique globally
- `barcode` and `variant_barcode` should be unique when present
- if `track_inventory = true`, inventory rows must exist for the chosen stock scope
- if `product_type = variable`, at least one variant-generating attribute must be selected
- attribute values assigned to a product must belong to that attribute
- variant attribute values must belong to the same product and same attribute
- attribute combinations cannot duplicate
- only one default variant per product
- `reserved_qty <= stock_qty` unless business rules explicitly allow oversell for backorders
- inactive attributes or inactive attribute values should not be attachable to new products
- a variant should not be active without at least one attribute combination

## 7. Admin Dashboard UI Layout

Recommended tab order inside `templates/dashboard/products/form.html`:

### Tab 1: Basic Info

Left column:

- product name
- slug
- product type
- category
- subcategory
- brand
- vendor display name
- SKU
- barcode
- short description
- full description

Right column:

- condition
- badges/tag builder
- rating average
- review count
- active toggle
- featured toggle
- size guide URL

### Tab 2: Media

- featured image uploader with preview
- gallery repeater with drag sort
- alt text per image
- variant image assignment table

### Tab 3: Pricing

- base price
- compare price
- cost price
- discount type/value
- tax class
- live price preview card showing:
  - current price
  - old price
  - save badge

### Tab 4: Inventory

- track inventory toggle
- stock scope toggle
- product-level inventory card for simple products
- per-variant stock summary for variable products
- low stock threshold
- allow backorder
- stock status
- availability label

### Tab 5: Attributes

- searchable selector for existing attributes
- quick-create modal for new attributes
- attribute row editor:
  - attribute name
  - attribute type
  - used for variants
  - display on product page
  - add or select values
- preview chips of selected values

### Tab 6: Variants

- "Generate Variants" action
- "Regenerate Missing Variants" action
- grid with one row per combination
- columns:
  - combination label
  - variant SKU
  - variant price
  - compare price
  - image
  - stock
  - reserved
  - status
  - default
  - active

### Tab 7: Specifications

- fixed common specification shortcuts:
  - brand
  - condition
  - weight
  - material
  - warranty
  - country of origin
- unlimited custom key/value rows

### Tab 8: SEO

- meta title
- meta description
- canonical URL
- OG title
- OG description
- OG image

## 8. UX Requirements

- attribute rows should support selecting an existing attribute or creating a new one inline
- value entry should support both existing values and new values in the same control
- variant generation should be one click and deterministic
- generated variants should remain editable after generation
- users should be able to disable specific combinations without deleting them
- per-variant stock should be visible from the variant table without opening a modal
- selectors should preview the exact combination label the customer will see
- specifications should support unlimited rows with drag ordering
- form should autosave slug from product name until the slug is manually edited
- if the product is simple, the variants tab should collapse or show a conversion action to variable product

## 9. Example Hoodie Product Data

```json
{
  "product_name": "EcoSmart Fleece Hoodie",
  "slug": "ecosmart-fleece-hoodie",
  "product_type": "variable",
  "category": "Fashion",
  "subcategory": "Hoodies",
  "brand": "Common Good",
  "vendor_display_name": "Common Good",
  "sku": "SPORT-6-FS",
  "barcode": "8901234567890",
  "short_description": "Premium quality fleece hoodie made from sustainable materials. Relaxed fit with kangaroo pocket.",
  "full_description": "The EcoSmart Fleece Hoodie blends everyday comfort with durable sustainable fabric.",
  "tags_badges": [
    { "label": "COMMON GOOD", "style": "brand" },
    { "label": "NEW", "style": "success" },
    { "label": "-30%", "style": "sale" }
  ],
  "condition": "new",
  "is_active": true,
  "is_featured": true,
  "base_price": "245.00",
  "compare_price": "350.00",
  "cost_price": "140.00",
  "discount_type": "percent",
  "discount_value": "30.00",
  "tax_class": "standard",
  "track_inventory": true,
  "stock_scope": "variant",
  "availability_label": "In Stock",
  "specifications": [
    { "key": "Weight", "value": "1.00 KGS" },
    { "key": "Material", "value": "80% Recycled Polyester, 20% Cotton" },
    { "key": "Country of Origin", "value": "Portugal" },
    { "key": "Warranty", "value": "30 Days Manufacturing Warranty" }
  ],
  "attributes": [
    {
      "attribute_name": "Color",
      "attribute_type": "color",
      "used_for_variants": true,
      "values": ["Charcoal", "Navy Blue", "Forest Green", "Burgundy", "Cream"]
    },
    {
      "attribute_name": "Size",
      "attribute_type": "size",
      "used_for_variants": true,
      "values": ["XS", "S", "M", "L", "XL", "XXL"]
    }
  ],
  "variants": [
    {
      "combination": ["Charcoal", "M"],
      "variant_sku": "SPORT-6-FS-CHA-M",
      "variant_price": "245.00",
      "variant_compare_price": "350.00",
      "stock_qty": 12,
      "reserved_qty": 2,
      "availability": "In Stock",
      "is_default": true,
      "is_active": true
    },
    {
      "combination": ["Cream", "XXL"],
      "variant_sku": "SPORT-6-FS-CRM-XXL",
      "variant_price": "245.00",
      "variant_compare_price": "350.00",
      "stock_qty": 0,
      "reserved_qty": 0,
      "availability": "Out of Stock",
      "is_default": false,
      "is_active": true
    }
  ]
}
```

## 10. Example Grocery Product Data

```json
{
  "product_name": "Organic Basmati Rice",
  "slug": "organic-basmati-rice",
  "product_type": "variable",
  "category": "Grocery",
  "subcategory": "Rice",
  "brand": "Harvest Pantry",
  "vendor_display_name": "Harvest Pantry",
  "sku": "RICE-BAS-ORG",
  "short_description": "Premium aged basmati rice with long grains and rich aroma.",
  "full_description": "Naturally aromatic basmati rice available in multiple pack sizes for households and retail shops.",
  "tags_badges": [
    { "label": "ORGANIC", "style": "success" },
    { "label": "BESTSELLER", "style": "brand" }
  ],
  "condition": "new",
  "is_active": true,
  "is_featured": false,
  "base_price": "4.50",
  "compare_price": "5.00",
  "cost_price": "3.20",
  "discount_type": "fixed",
  "discount_value": "0.50",
  "tax_class": "zero",
  "track_inventory": true,
  "stock_scope": "variant",
  "availability_label": "In Stock",
  "specifications": [
    { "key": "Country of Origin", "value": "India" },
    { "key": "Storage", "value": "Keep in a cool, dry place" },
    { "key": "Shelf Life", "value": "12 Months" }
  ],
  "attributes": [
    {
      "attribute_name": "Weight",
      "attribute_type": "number",
      "used_for_variants": true,
      "values": ["1kg", "2kg", "5kg"]
    }
  ],
  "variants": [
    {
      "combination": ["1kg"],
      "variant_sku": "RICE-BAS-ORG-1KG",
      "variant_price": "4.50",
      "variant_compare_price": "5.00",
      "stock_qty": 40,
      "reserved_qty": 4,
      "availability": "In Stock",
      "is_default": true,
      "is_active": true
    },
    {
      "combination": ["2kg"],
      "variant_sku": "RICE-BAS-ORG-2KG",
      "variant_price": "8.50",
      "variant_compare_price": "9.50",
      "stock_qty": 28,
      "reserved_qty": 2,
      "availability": "In Stock",
      "is_default": false,
      "is_active": true
    },
    {
      "combination": ["5kg"],
      "variant_sku": "RICE-BAS-ORG-5KG",
      "variant_price": "19.99",
      "variant_compare_price": "22.00",
      "stock_qty": 8,
      "reserved_qty": 1,
      "availability": "Only 7 Left",
      "is_default": false,
      "is_active": true
    }
  ]
}
```

## 11. Implementation Recommendation For This Repo

Minimal production-ready sequence for this codebase:

1. Extend `catalog.models` with `Product`, `ProductImage`, `ProductSpecification`, `ProductAttribute`, `ProductAttributeValue`, `ProductVariant`, `ProductVariantAttributeValue`, and `Inventory`.
2. Add migrations in `catalog/migrations`.
3. Build `ProductForm` plus inline formsets or JSON-backed repeaters for:
   - images
   - specifications
   - product attributes
   - variants
4. Add dashboard routes:
   - `dashboard/products/`
   - `dashboard/products/add/`
   - `dashboard/products/<pk>/edit/`
5. Add `templates/dashboard/products/list.html` and `templates/dashboard/products/form.html`.
6. Add a service layer for:
   - slug generation
   - badge normalization
   - variant matrix generation
   - inventory sync
   - storefront payload building
7. Replace hardcoded content in product detail templates with a `product` object and selected variant context.

This architecture stays generic and supports fashion, grocery, electronics, cosmetics, and any future attribute family without hardcoding color-and-size-only logic.
