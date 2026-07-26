import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from sitepages.models import UserProfile


class AuditUnusedMediaCommandTests(TestCase):
    def setUp(self):
        self.media_root = Path(tempfile.mkdtemp(prefix="revo-media-audit-"))
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        user = get_user_model().objects.create_user(username="media-audit@example.com")
        self.profile = UserProfile.objects.get(user=user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def write_file(self, name, content=b"image-data"):
        path = self.media_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_dry_run_reports_orphans_missing_references_and_duplicates_without_deleting(self):
        self.profile.image.name = "user_profiles/referenced.jpg"
        self.profile.save(update_fields=["image"])
        self.write_file("user_profiles/referenced.jpg", b"same")
        orphan = self.write_file("orphan.jpg", b"same")
        self.profile.image.name = "user_profiles/missing.jpg"
        UserProfile.objects.filter(pk=self.profile.pk).update(image=self.profile.image.name)
        protected = self.write_file("placeholder-default.jpg", b"protected")

        output = StringIO()
        call_command("audit_unused_media", stdout=output)

        report = output.getvalue()
        self.assertIn("Media audit (dry-run)", report)
        self.assertIn("ORPHAN orphan.jpg", report)
        self.assertIn("MISSING user_profiles/missing.jpg", report)
        self.assertIn("PROTECTED placeholder-default.jpg", report)
        self.assertIn("Exact duplicate groups: 1", report)
        self.assertTrue(orphan.exists())
        self.assertTrue(protected.exists())

    def test_delete_removes_only_orphans(self):
        self.profile.image.name = "user_profiles/referenced.jpg"
        self.profile.save(update_fields=["image"])
        referenced = self.write_file("user_profiles/referenced.jpg")
        orphan = self.write_file("old/orphan.jpg")
        protected = self.write_file("defaults/fallback.jpg")

        output = StringIO()
        call_command("audit_unused_media", delete=True, stdout=output)

        self.assertTrue(referenced.exists())
        self.assertFalse(orphan.exists())
        self.assertTrue(protected.exists())
        self.assertIn("Deleted 1 orphaned files.", output.getvalue())
