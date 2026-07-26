import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from sitepages.management.commands.audit_media import Command, resolve_inside_media_root
from sitepages.models import UserProfile


class AuditMediaCommandTests(TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(prefix="revo-audit-media-")
        self.media_root = Path(self.temp_directory.name)
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MEDIA_AUDIT_PROTECTED_FILES=("protected/custom.jpg",),
        )
        self.settings_override.enable()
        self.profile_number = 0

    def tearDown(self):
        self.settings_override.disable()
        self.temp_directory.cleanup()

    def create_profile(self, image_value=""):
        self.profile_number += 1
        user = get_user_model().objects.create_user(
            username=f"audit-media-{self.profile_number}@example.com"
        )
        profile = UserProfile.objects.get(user=user)
        UserProfile.objects.filter(pk=profile.pk).update(image=image_value)
        profile.refresh_from_db()
        return profile

    def write_file(self, relative_name, content=b"media-content"):
        path = self.media_root / Path(*relative_name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def run_command(self, **options):
        output = StringIO()
        call_command("audit_media", stdout=output, **options)
        return output.getvalue()

    def test_dry_run_does_not_delete_and_detects_orphan(self):
        orphan = self.write_file("orphan.jpg")

        report = self.run_command()

        self.assertTrue(orphan.exists())
        self.assertIn("Mode: dry-run", report)
        self.assertIn("Orphan file count: 1", report)
        self.assertIn("  orphan.jpg", report)
        self.assertIn("Files deleted:\n  (none)", report)

    def test_referenced_files_are_retained_and_reference_details_are_reported(self):
        profile = self.create_profile("user_profiles/referenced.jpg")
        referenced = self.write_file("user_profiles/referenced.jpg")

        report = self.run_command()

        self.assertTrue(referenced.exists())
        self.assertIn("Referenced file count: 1", report)
        self.assertIn(f"sitepages.UserProfile.image[pk={profile.pk}]", report)
        self.assertNotIn("Orphan file count: 1", report)

    def test_missing_references_are_reported(self):
        self.create_profile("user_profiles/missing.jpg")

        report = self.run_command()

        self.assertIn("Missing referenced file count: 1", report)
        self.assertIn("  user_profiles/missing.jpg", report)

    def test_exact_duplicates_are_detected_by_sha256(self):
        self.write_file("duplicates/one.jpg", b"identical")
        self.write_file("duplicates/two.jpg", b"identical")
        self.write_file("duplicates/different.jpg", b"different")

        report = self.run_command()

        self.assertIn("Exact duplicate groups: 1", report)
        self.assertIn("duplicates/one.jpg", report)
        self.assertIn("duplicates/two.jpg", report)

    def test_external_image_urls_are_ignored(self):
        self.create_profile("https://cdn.example.com/profile.jpg")

        report = self.run_command()

        self.assertIn("External URL references ignored: 1", report)
        self.assertIn("https://cdn.example.com/profile.jpg", report)
        self.assertIn("Missing referenced file count: 0", report)

    def test_delete_orphans_deletes_only_unreferenced_unprotected_files(self):
        self.create_profile("user_profiles/referenced.jpg")
        referenced = self.write_file("user_profiles/referenced.jpg")
        orphan = self.write_file("old/orphan.jpg")
        gitkeep = self.write_file(".gitkeep", b"")
        placeholder = self.write_file("placeholder-image.jpg")
        configured = self.write_file("protected/custom.jpg")

        report = self.run_command(delete_orphans=True, yes=True)

        self.assertTrue(referenced.exists())
        self.assertFalse(orphan.exists())
        self.assertTrue(gitkeep.exists())
        self.assertTrue(placeholder.exists())
        self.assertTrue(configured.exists())
        self.assertIn("Files deleted:\n  old/orphan.jpg", report)

    def test_deduplication_updates_database_fields_and_deletes_redundant_file(self):
        first = self.create_profile("duplicates/a.jpg")
        second = self.create_profile("duplicates/b.jpg")
        canonical = self.write_file("duplicates/a.jpg", b"same-file")
        redundant = self.write_file("duplicates/b.jpg", b"same-file")

        report = self.run_command(deduplicate=True, yes=True)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.image.name, "duplicates/a.jpg")
        self.assertEqual(second.image.name, "duplicates/a.jpg")
        self.assertTrue(canonical.exists())
        self.assertFalse(redundant.exists())
        self.assertIn(
            f"sitepages.UserProfile.image[pk={second.pk}]: duplicates/b.jpg -> duplicates/a.jpg",
            report,
        )

    def test_deduplication_rolls_back_database_and_files_when_cleanup_fails(self):
        first = self.create_profile("duplicates/a.jpg")
        second = self.create_profile("duplicates/b.jpg")
        canonical = self.write_file("duplicates/a.jpg", b"same-file")
        redundant = self.write_file("duplicates/b.jpg", b"same-file")

        with patch.object(Command, "_delete_staged_file", side_effect=OSError("simulated failure")):
            with self.assertRaisesMessage(CommandError, "was rolled back"):
                self.run_command(deduplicate=True, yes=True)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.image.name, "duplicates/a.jpg")
        self.assertEqual(second.image.name, "duplicates/b.jpg")
        self.assertTrue(canonical.exists())
        self.assertTrue(redundant.exists())
        self.assertEqual(canonical.read_bytes(), redundant.read_bytes())

    def test_paths_outside_media_root_are_rejected_and_untouched(self):
        outside = self.media_root.parent / "outside-audit-media.jpg"
        outside.write_bytes(b"outside")
        try:
            with self.assertRaises(CommandError):
                resolve_inside_media_root(self.media_root, "../outside-audit-media.jpg")
            self.assertTrue(outside.exists())
        finally:
            outside.unlink(missing_ok=True)

    def test_output_report_writes_full_report(self):
        self.write_file("orphan.jpg")
        report_path = Path(self.temp_directory.name) / "reports" / "media-audit.txt"

        self.run_command(output_report=str(report_path))

        self.assertTrue(report_path.exists())
        saved = report_path.read_text(encoding="utf-8")
        self.assertIn("Total media files: 1", saved)
        self.assertIn("Orphan file count: 1", saved)
