import hashlib
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import FileField


DEFAULT_PROTECTED_PATTERNS = (
    ".gitkeep",
    "default*",
    "defaults/*",
    "defaults/**/*",
    "placeholder*",
    "placeholders/*",
    "placeholders/**/*",
)


@dataclass(frozen=True)
class MediaReference:
    model: type
    field: FileField
    pk: object
    stored_value: str
    normalized_path: str

    @property
    def label(self):
        return f"{self.model._meta.label}.{self.field.name}[pk={self.pk}]"


@dataclass
class DuplicateAction:
    digest: str
    canonical: str
    redundant: list[str]


@dataclass
class AuditState:
    media_root: Path
    disk_files: dict[str, Path]
    references: dict[str, list[MediaReference]]
    external_references: list[tuple[str, str, object, str]]
    unsafe_references: list[tuple[str, str, object, str]]
    protected: set[str]
    referenced: set[str]
    orphaned: set[str]
    missing: set[str]
    duplicate_groups: dict[str, list[str]]
    total_size: int
    recoverable_size: int
    files_deleted: list[str] = field(default_factory=list)
    references_updated: list[str] = field(default_factory=list)


def is_external_url(value):
    value = str(value or "").strip()
    parsed = urlsplit(value)
    return parsed.scheme.lower() in {"http", "https"} or value.startswith("//")


def normalize_media_path(value):
    value = str(value or "").strip().replace("\\", "/")
    if not value or is_external_url(value):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe local media path: {value}")
    return path.as_posix()


def resolve_inside_media_root(media_root, relative_name, *, must_exist=False):
    try:
        normalized = normalize_media_path(relative_name)
    except ValueError as error:
        raise CommandError(str(error)) from error
    if not normalized:
        raise CommandError(f"Not a local media path: {relative_name}")
    candidate = (media_root / Path(*PurePosixPath(normalized).parts)).resolve(strict=must_exist)
    try:
        candidate.relative_to(media_root)
    except ValueError as error:
        raise CommandError(f"Path resolves outside MEDIA_ROOT: {relative_name}") from error
    return candidate


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
    help = "Audit MEDIA_ROOT and optionally perform confirmed, reference-safe cleanup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Delete unreferenced, unprotected files after confirmation.",
        )
        parser.add_argument(
            "--deduplicate",
            action="store_true",
            help="Transactionally repoint exact duplicate references and remove redundant copies.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation for requested destructive actions.",
        )
        parser.add_argument(
            "--output-report",
            metavar="PATH",
            help="Write the complete UTF-8 audit report to PATH.",
        )

    def handle(self, *args, **options):
        if options["yes"] and not (options["delete_orphans"] or options["deduplicate"]):
            raise CommandError("--yes is only valid with --delete-orphans or --deduplicate")

        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not media_root.exists() or not media_root.is_dir():
            raise CommandError(f"MEDIA_ROOT does not exist or is not a directory: {media_root}")

        state = self.build_audit_state(media_root)
        dedup_actions = self.build_duplicate_actions(state)
        dedup_paths = {
            name for action in dedup_actions for name in action.redundant if name not in state.protected
        }
        recoverable_paths = state.orphaned | dedup_paths
        state.recoverable_size = sum(
            state.disk_files[name].stat().st_size for name in recoverable_paths
        )
        orphan_targets = []
        if options["delete_orphans"]:
            # Deduplication handles its own redundant paths. A plain orphan
            # cleanup must not skip a file just because its bytes match another.
            excluded_paths = dedup_paths if options["deduplicate"] else set()
            orphan_targets = sorted(state.orphaned - excluded_paths)
        dedup_targets = sorted(dedup_paths) if options["deduplicate"] else []
        destructive_targets = sorted(set(orphan_targets) | set(dedup_targets))

        if options["delete_orphans"] or options["deduplicate"]:
            recoverable = sum(state.disk_files[name].stat().st_size for name in destructive_targets)
            self.stdout.write("Planned media cleanup:")
            self.stdout.write(f"  Files: {len(destructive_targets)}")
            self.stdout.write(f"  Recoverable disk space: {recoverable} bytes")
            for name in destructive_targets:
                self.stdout.write(f"  DELETE {name}")
            if not destructive_targets:
                self.stdout.write("  No eligible files will be deleted.")
            if destructive_targets and not options["yes"]:
                answer = input('Type "yes" to continue: ').strip().lower()
                if answer != "yes":
                    raise CommandError("Media cleanup cancelled; no files were changed.")

        if options["deduplicate"] and dedup_actions:
            self.perform_deduplication(state, dedup_actions)
        if options["delete_orphans"] and orphan_targets:
            self.delete_orphans(state, orphan_targets)

        if options["delete_orphans"] or options["deduplicate"]:
            requested = []
            if options["delete_orphans"]:
                requested.append("delete-orphans")
            if options["deduplicate"]:
                requested.append("deduplicate")
            mode = " + ".join(requested)
        else:
            mode = "dry-run"
        report = self.render_report(state, mode)
        self.stdout.write(report)
        if options["output_report"]:
            report_path = Path(options["output_report"]).expanduser().resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report + "\n", encoding="utf-8")
            self.stdout.write(f"Report written to: {report_path}")

    def protected_patterns(self):
        configured = tuple(getattr(settings, "MEDIA_AUDIT_PROTECTED_FILES", ()))
        legacy = tuple(getattr(settings, "MEDIA_AUDIT_PROTECTED_PATHS", ()))
        return DEFAULT_PROTECTED_PATTERNS + configured + legacy

    def build_audit_state(self, media_root):
        references = defaultdict(list)
        external = []
        unsafe = []
        for model in apps.get_models():
            file_fields = [field for field in model._meta.get_fields() if isinstance(field, FileField)]
            for file_field in file_fields:
                rows = (
                    model._default_manager.exclude(**{file_field.name: ""})
                    .exclude(**{file_field.name: None})
                    .values_list("pk", file_field.name)
                )
                for pk, raw_value in rows.iterator():
                    stored_value = str(raw_value or "").strip()
                    if not stored_value:
                        continue
                    if is_external_url(stored_value):
                        external.append((model._meta.label, file_field.name, pk, stored_value))
                        continue
                    try:
                        normalized = normalize_media_path(stored_value)
                    except ValueError:
                        unsafe.append((model._meta.label, file_field.name, pk, stored_value))
                        continue
                    reference = MediaReference(model, file_field, pk, stored_value, normalized)
                    references[normalized].append(reference)

        disk_files = {}
        total_size = 0
        for candidate in media_root.rglob("*"):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(media_root)
            except ValueError as error:
                raise CommandError(f"Discovered file outside MEDIA_ROOT: {candidate}") from error
            name = candidate.relative_to(media_root).as_posix()
            disk_files[name] = candidate
            total_size += candidate.stat().st_size

        disk_names = set(disk_files)
        referenced = set(references) & disk_names
        missing = set(references) - disk_names
        protected = {name for name in disk_names if is_protected(name, self.protected_patterns())}
        orphaned = disk_names - set(references) - protected

        hash_groups = defaultdict(list)
        for name, path in disk_files.items():
            hash_groups[sha256_file(path)].append(name)
        duplicates = {
            digest: sorted(names)
            for digest, names in hash_groups.items()
            if len(names) > 1
        }
        recoverable_size = sum(disk_files[name].stat().st_size for name in orphaned)
        return AuditState(
            media_root=media_root,
            disk_files=disk_files,
            references=dict(references),
            external_references=external,
            unsafe_references=unsafe,
            protected=protected,
            referenced=referenced,
            orphaned=orphaned,
            missing=missing,
            duplicate_groups=duplicates,
            total_size=total_size,
            recoverable_size=recoverable_size,
        )

    def build_duplicate_actions(self, state):
        actions = []
        for digest, names in sorted(state.duplicate_groups.items()):
            # Prefer an already referenced path to minimize database changes;
            # then prefer a protected copy so it can never become redundant.
            canonical = min(
                names,
                key=lambda name: (
                    name not in state.references,
                    name not in state.protected,
                    name.casefold(),
                    name,
                ),
            )
            redundant = [
                name for name in names if name != canonical and name not in state.protected
            ]
            if redundant:
                actions.append(DuplicateAction(digest, canonical, redundant))
        return actions

    def perform_deduplication(self, state, actions):
        update_plan = []
        file_plan = []
        for action in actions:
            canonical_path = resolve_inside_media_root(
                state.media_root, action.canonical, must_exist=True
            )
            if not canonical_path.is_file() or canonical_path.is_symlink():
                raise CommandError(f"Unsafe canonical duplicate: {action.canonical}")
            for redundant_name in action.redundant:
                if redundant_name in state.protected:
                    continue
                redundant_path = resolve_inside_media_root(
                    state.media_root, redundant_name, must_exist=True
                )
                if not redundant_path.is_file() or redundant_path.is_symlink():
                    raise CommandError(f"Unsafe redundant duplicate: {redundant_name}")
                file_plan.append((action.canonical, redundant_name, redundant_path))
                for reference in state.references.get(redundant_name, []):
                    update_plan.append((reference, action.canonical))

        if not file_plan and not update_plan:
            return

        rollback_dir = state.media_root / f".audit_media_rollback_{uuid.uuid4().hex}"
        rollback_dir.mkdir(mode=0o700)
        staged = []
        committed = False
        try:
            with transaction.atomic():
                for reference, canonical in update_plan:
                    updated = reference.model._default_manager.filter(pk=reference.pk).update(
                        **{reference.field.name: canonical}
                    )
                    if updated != 1:
                        raise CommandError(f"Could not update {reference.label}")
                for index, (canonical, redundant_name, redundant_path) in enumerate(file_plan):
                    staged_path = rollback_dir / f"{index:08d}.bak"
                    self._stage_file(redundant_path, staged_path)
                    staged.append((canonical, redundant_name, redundant_path, staged_path))
            committed = True

            for _canonical, _redundant_name, _original, staged_path in staged:
                self._delete_staged_file(staged_path)
        except Exception as error:
            rollback_errors = self._rollback_deduplication(
                update_plan=update_plan,
                staged=staged,
                committed=committed,
                state=state,
            )
            detail = f"Deduplication failed and was rolled back: {error}"
            if rollback_errors:
                detail += f"; rollback errors: {'; '.join(rollback_errors)}"
            raise CommandError(detail) from error
        finally:
            if rollback_dir.exists() and not any(rollback_dir.iterdir()):
                rollback_dir.rmdir()

        for reference, canonical in update_plan:
            message = f"{reference.label}: {reference.stored_value} -> {canonical}"
            state.references_updated.append(message)
        for _canonical, redundant_name, _original, _staged_path in staged:
            state.files_deleted.append(redundant_name)

    def _stage_file(self, original, staged_path):
        original.replace(staged_path)

    def _delete_staged_file(self, staged_path):
        staged_path.unlink()

    def _rollback_deduplication(self, *, update_plan, staged, committed, state):
        errors = []
        for canonical, _redundant_name, original, staged_path in reversed(staged):
            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                if staged_path.exists():
                    staged_path.replace(original)
                elif committed and not original.exists():
                    canonical_path = resolve_inside_media_root(
                        state.media_root, canonical, must_exist=True
                    )
                    shutil.copy2(canonical_path, original)
            except Exception as restore_error:  # pragma: no cover - catastrophic I/O failure
                errors.append(f"file {original}: {restore_error}")

        if committed:
            try:
                with transaction.atomic():
                    for reference, _canonical in update_plan:
                        reference.model._default_manager.filter(pk=reference.pk).update(
                            **{reference.field.name: reference.stored_value}
                        )
            except Exception as database_error:  # pragma: no cover - database outage
                errors.append(f"database: {database_error}")
        return errors

    def delete_orphans(self, state, orphan_targets):
        for name in orphan_targets:
            if name not in state.orphaned or name in state.references or name in state.protected:
                raise CommandError(f"Refusing to delete non-orphan or protected file: {name}")
            path = resolve_inside_media_root(state.media_root, name, must_exist=True)
            if not path.is_file() or path.is_symlink():
                raise CommandError(f"Refusing to delete non-regular file: {name}")
            path.unlink()
            state.files_deleted.append(name)

    def render_report(self, state, mode):
        lines = [
            "Media audit report",
            f"Mode: {mode}",
            f"MEDIA_ROOT: {state.media_root}",
            f"Total media files: {len(state.disk_files)}",
            f"Total media size: {state.total_size} bytes",
            f"Referenced file count: {len(state.referenced)}",
            f"Orphan file count: {len(state.orphaned)}",
            f"Missing referenced file count: {len(state.missing)}",
            f"Exact duplicate groups: {len(state.duplicate_groups)}",
            f"Recoverable disk space: {state.recoverable_size} bytes",
            f"External URL references ignored: {len(state.external_references)}",
            f"Unsafe database paths ignored: {len(state.unsafe_references)}",
            f"Protected files: {len(state.protected)}",
            "",
            "Database references:",
        ]
        if state.references:
            for name in sorted(state.references):
                lines.append(f"  {name}")
                for reference in state.references[name]:
                    lines.append(f"    {reference.label} stored={reference.stored_value}")
        else:
            lines.append("  (none)")

        lines.extend(["", "Referenced files:"])
        lines.extend(f"  {name}" for name in sorted(state.referenced))
        if not state.referenced:
            lines.append("  (none)")
        lines.extend(["", "Orphan files:"])
        lines.extend(f"  {name}" for name in sorted(state.orphaned))
        if not state.orphaned:
            lines.append("  (none)")
        lines.extend(["", "Missing referenced files:"])
        for name in sorted(state.missing):
            lines.append(f"  {name}")
            for reference in state.references[name]:
                lines.append(f"    {reference.label}")
        if not state.missing:
            lines.append("  (none)")
        lines.extend(["", "Exact duplicate groups:"])
        for digest, names in sorted(state.duplicate_groups.items()):
            lines.append(f"  SHA256 {digest}")
            for name in names:
                status = "referenced" if name in state.references else "unreferenced"
                if name in state.protected:
                    status += ", protected"
                lines.append(f"    {name} [{status}]")
        if not state.duplicate_groups:
            lines.append("  (none)")
        lines.extend(["", "External URL references ignored:"])
        lines.extend(
            f"  {model}.{field}[pk={pk}] {value}"
            for model, field, pk, value in state.external_references
        )
        if not state.external_references:
            lines.append("  (none)")
        lines.extend(["", "Protected files:"])
        lines.extend(f"  {name}" for name in sorted(state.protected))
        if not state.protected:
            lines.append("  (none)")
        lines.extend(["", "Files deleted:"])
        lines.extend(f"  {name}" for name in state.files_deleted)
        if not state.files_deleted:
            lines.append("  (none)")
        lines.extend(["", "Database references updated:"])
        lines.extend(f"  {message}" for message in state.references_updated)
        if not state.references_updated:
            lines.append("  (none)")
        return "\n".join(lines)
