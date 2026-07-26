from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils.text import slugify
from PIL import Image, ImageOps


class CompanyProfile(models.Model):
    LOGO_SIZE = (240, 80)

    company_name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    logo = models.ImageField(upload_to="company/logos/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "company_name", "id"]
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profiles"

    def __str__(self):
        return self.company_name

    @classmethod
    def build_unique_slug(cls, value, instance=None):
        base_slug = slugify(value) or "company"
        slug = base_slug
        queryset = cls.objects.all()

        if instance and instance.pk:
            queryset = queryset.exclude(pk=instance.pk)

        suffix = 2
        while queryset.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).order_by("sort_order", "company_name", "id").first()

    @classmethod
    def get_singleton(cls):
        return cls.objects.order_by("-logo", "-is_active", "-updated_at", "id").first()

    def clean(self):
        super().clean()
        queryset = CompanyProfile.objects.all()
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        if queryset.exists():
            raise ValidationError("Only one company profile can be created. Edit the existing profile instead.")

    def save(self, *args, **kwargs):
        queryset = CompanyProfile.objects.all()
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        if queryset.exists():
            raise ValidationError("Only one company profile can be created. Edit the existing profile instead.")

        self.slug = self.build_unique_slug(self.company_name, instance=self)
        if self.logo:
            self.normalize_logo()
        super().save(*args, **kwargs)

    def normalize_logo(self):
        self.logo.open()
        image = None
        normalized = None
        output = BytesIO()

        try:
            image = Image.open(self.logo)
            image = ImageOps.exif_transpose(image)

            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

            if image.mode == "RGBA":
                content_box = image.getbbox()
                if content_box:
                    image = image.crop(content_box)

            normalized = ImageOps.contain(image, self.LOGO_SIZE, Image.Resampling.LANCZOS)
            normalized.save(output, format="PNG", optimize=True)
            output.seek(0)

            file_stem = slugify(self.company_name) or "company-logo"
            self.logo.save(f"{file_stem}.png", ContentFile(output.read()), save=False)
        finally:
            if image is not None:
                image.close()
            if normalized is not None:
                normalized.close()
            output.close()
            self.logo.close()
