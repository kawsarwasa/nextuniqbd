import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from PIL import Image

from blog.models import BlogCategory, BlogPost, BlogPostImage
from category.models import Brand
from sitepages.models import HeroSlide


def uploaded_image(filename, color):
    buffer = BytesIO()
    Image.new("RGB", (40, 40), color).save(buffer, format="JPEG")
    return SimpleUploadedFile(filename, buffer.getvalue(), content_type="image/jpeg")


class MediaCleanupTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.media_directory = tempfile.TemporaryDirectory(prefix="revo-media-cleanup-")
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def test_brand_logo_is_removed_when_replaced_and_deleted(self):
        brand = Brand.objects.create(name="Acme", logo=uploaded_image("old.jpg", "red"))
        old_logo_path = Path(brand.logo.path)

        brand.logo = uploaded_image("new.jpg", "blue")
        brand.save()

        self.assertFalse(old_logo_path.exists())
        new_logo_path = Path(brand.logo.path)
        self.assertTrue(new_logo_path.exists())

        brand.delete()
        self.assertFalse(new_logo_path.exists())

    def test_replaced_gallery_image_is_removed(self):
        post = BlogPost.objects.create(
            category=BlogCategory.objects.create(name="News"),
            title="Release notes",
        )
        gallery_image = BlogPostImage.objects.create(
            post=post,
            image=uploaded_image("old-gallery.jpg", "red"),
        )
        old_image_path = Path(gallery_image.image.path)

        gallery_image.image = uploaded_image("new-gallery.jpg", "blue")
        gallery_image.save()

        self.assertFalse(old_image_path.exists())
        self.assertTrue(Path(gallery_image.image.path).exists())

    def test_hero_slide_image_is_removed_on_delete(self):
        slide = HeroSlide.objects.create(
            name="Summer",
            title="Summer sale",
            image=uploaded_image("slide.jpg", "red"),
        )
        slide_path = Path(slide.image.path)
        slide.delete()
        self.assertFalse(slide_path.exists())
