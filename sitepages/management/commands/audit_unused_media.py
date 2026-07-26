import hashlib
from collections import defaultdict
from pathlib import Path, PurePosixPath

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField


DEFAULT_PROTECTED_PATTERNS = (".gitkeep", "default*", "defaults/*", "placeholder*")


def normalize_media_name(value):
    return str(value or "").replace("\\", "/").lstrip("/")


def is_protected(name, patterns):
    path = PurePosixPath(name)
    return any(path.match(pattern) or path.name == pattern for pattern in patterns)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Audit database file references against MEDIA_ROOT; dry-run unless --delete is supplied."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete orphaned files after reporting them. Without this flag nothing is deleted.",
        )
        parser.add_argument(
            "--protect",
            action="append",
            default=[],
            metavar="GLOB",
            help="Additional MEDIA_ROOT-relative protected glob (repeatable).",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not media_root.exists():
            raise CommandError(f"MEDIA_ROOT does not exist: {media_root}")
        if not media_root.is_dir():
            raise CommandError(f"MEDIA_ROOT is not a directory: {media_root}")

        configured_patterns = tuple(getattr(settings, "MEDIA_AUDIT_PROTECTED_PATHS", ()))
        protected_patterns = DEFAULT_PROTECTED_PATTERNS + configured_patterns + tuple(options["protect"])
        referenced = set()
        reference_rows = 0

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, FileField):
                    continue
                values = (
                    model._default_manager.exclude(**{field.name: ""})
                    .exclude(**{field.name: None})
                    .values_list(field.name, flat=True)
                )
                for value in values.iterator():
                    name = normalize_media_name(value)
                    if name:
                        referenced.add(name)
                        reference_rows += 1

        disk_files = {}
        for path in media_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(media_root)
            except ValueError as error:
                raise CommandError(f"Unsafe media path outside MEDIA_ROOT: {path}") from error
            disk_files[path.relative_to(media_root).as_posix()] = path

        disk_names = set(disk_files)
        missing = sorted(referenced - disk_names)
        protected = sorted(name for name in disk_names if is_protected(name, protected_patterns))
        orphaned = sorted(disk_names - referenced - set(protected))

        hashes = defaultdict(list)
        for name, path in disk_files.items():
            hashes[sha256_file(path)].append(name)
        duplicates = {digest: sorted(names) for digest, names in hashes.items() if len(names) > 1}
        recoverable = sum(disk_files[name].stat().st_size for name in orphaned)

        self.stdout.write("Media audit (DELETE enabled)" if options["delete"] else "Media audit (dry-run)")
        self.stdout.write(f"MEDIA_ROOT: {media_root}")
        self.stdout.write(f"Database file references: {reference_rows} rows / {len(referenced)} unique paths")
        self.stdout.write(f"Files on disk: {len(disk_names)}")
        self.stdout.write(f"Orphaned files: {len(orphaned)}")
        for name in orphaned:
            self.stdout.write(f"  ORPHAN {name}")
        self.stdout.write(f"Missing referenced files: {len(missing)}")
        for name in missing:
            self.stdout.write(f"  MISSING {name}")
        self.stdout.write(f"Protected files: {len(protected)}")
        for name in protected:
            self.stdout.write(f"  PROTECTED {name}")
        self.stdout.write(f"Exact duplicate groups: {len(duplicates)}")
        for digest, names in sorted(duplicates.items()):
            self.stdout.write(f"  SHA256 {digest}")
            for name in names:
                self.stdout.write(f"    {name}")
        self.stdout.write(f"Total recoverable disk space: {recoverable} bytes")

        if options["delete"]:
            deleted = 0
            for name in orphaned:
                disk_files[name].unlink()
                deleted += 1
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} orphaned files."))
        else:
            self.stdout.write("No files deleted. Re-run with --delete only after reviewing this report.")
