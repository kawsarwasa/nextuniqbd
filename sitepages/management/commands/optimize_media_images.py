from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = "Preview or write non-destructive WebP sidecars for MEDIA_ROOT images. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Write WebP sidecars; originals are never replaced.")
        parser.add_argument("--force", action="store_true", help="Replace existing WebP sidecars when used with --write.")
        parser.add_argument("--quality", type=int, default=82, help="WebP quality from 1 to 100 (default: 82).")
        parser.add_argument(
            "--min-size",
            type=int,
            default=150 * 1024,
            help="Only inspect source files at least this many bytes (default: 153600).",
        )

    def handle(self, *args, **options):
        quality = options["quality"]
        if not 1 <= quality <= 100:
            raise CommandError("--quality must be between 1 and 100")
        if options["min_size"] < 0:
            raise CommandError("--min-size cannot be negative")

        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not media_root.is_dir():
            raise CommandError(f"MEDIA_ROOT does not exist or is not a directory: {media_root}")

        mode = "WRITE" if options["write"] else "DRY-RUN"
        self.stdout.write(f"Image optimization ({mode}); originals are preserved")
        candidates = written = skipped = 0
        projected_savings = 0

        for source in sorted(media_root.rglob("*")):
            if (
                not source.is_file()
                or source.is_symlink()
                or source.suffix.lower() not in SUPPORTED_SUFFIXES
                or source.stat().st_size < options["min_size"]
                or source.name.lower().endswith(".optimized.webp")
            ):
                continue
            candidates += 1
            target = source.with_name(f"{source.stem}.optimized.webp")
            relative_source = source.relative_to(media_root).as_posix()
            relative_target = target.relative_to(media_root).as_posix()
            if target.exists() and not options["force"]:
                self.stdout.write(f"  SKIP existing {relative_target}")
                skipped += 1
                continue

            try:
                with Image.open(source) as opened:
                    if getattr(opened, "is_animated", False):
                        self.stdout.write(f"  SKIP animated {relative_source}")
                        skipped += 1
                        continue
                    image = ImageOps.exif_transpose(opened)
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    output = BytesIO()
                    image.save(output, format="WEBP", quality=quality, method=6)
                    optimized = output.getvalue()
            except (OSError, UnidentifiedImageError) as error:
                self.stdout.write(f"  SKIP unreadable {relative_source}: {error}")
                skipped += 1
                continue

            source_size = source.stat().st_size
            saving = source_size - len(optimized)
            if saving <= 0:
                self.stdout.write(f"  SKIP no saving {relative_source} ({source_size} -> {len(optimized)} bytes)")
                skipped += 1
                continue
            projected_savings += saving
            self.stdout.write(f"  {relative_source} -> {relative_target}: {source_size} -> {len(optimized)} bytes")
            if options["write"]:
                target.write_bytes(optimized)
                written += 1

        self.stdout.write(f"Candidates: {candidates}; written: {written}; skipped: {skipped}")
        self.stdout.write(f"Projected recoverable transfer/storage: {projected_savings} bytes")
        if not options["write"]:
            self.stdout.write("No files written. Re-run with --write to create sidecars after review.")
