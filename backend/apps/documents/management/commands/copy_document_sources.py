"""Copy legacy local sources to configured object storage without changing keys."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.documents.models import Document


def digest(stream):
    hasher = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        hasher.update(chunk)
    return hasher.hexdigest()


class Command(BaseCommand):
    help = "Verify or copy legacy MEDIA_ROOT files to S3 using their existing Document.file keys."

    def add_arguments(self, parser):
        parser.add_argument("--source-media-root", required=True)
        parser.add_argument("--apply", action="store_true", help="Copy missing objects after validation; default is dry run.")

    def handle(self, *args, **options):
        if settings.DOCUMENT_STORAGE_BACKEND != "s3":
            raise CommandError("Configure S3 document storage before copying sources.")
        root = Path(options["source_media_root"]).resolve(strict=True)
        if not root.is_dir():
            raise CommandError("Source media root must be a directory.")
        verified = copied = pending = 0
        for document in Document.objects.exclude(file="").iterator(chunk_size=100):
            key = document.file.name
            if not key.startswith("documents/") or ".." in key.split("/"):
                raise CommandError(f"Document {document.pk} has an invalid storage key.")
            try:
                if default_storage.exists(key):
                    with default_storage.open(key, "rb") as source:
                        if digest(source) != document.sha256:
                            raise CommandError(f"Document {document.pk} has a mismatched object digest.")
                    verified += 1
                    continue
                path = (root / key).resolve()
                if root not in path.parents or not path.is_file():
                    raise CommandError(f"Document {document.pk} has no matching local source.")
                with path.open("rb") as source:
                    if digest(source) != document.sha256:
                        raise CommandError(f"Document {document.pk} has a mismatched local digest.")
                if options["apply"]:
                    with path.open("rb") as source:
                        saved_key = default_storage.save(key, File(source))
                    if saved_key != key:
                        raise CommandError(f"Document {document.pk} could not retain its storage key.")
                    with default_storage.open(key, "rb") as source:
                        if digest(source) != document.sha256:
                            raise CommandError(f"Document {document.pk} failed copied-object verification.")
                    copied += 1
                else:
                    pending += 1
            except CommandError:
                raise
            except Exception as exc:
                raise CommandError(f"Storage operation failed for document {document.pk}.") from exc
        self.stdout.write(f"Verified {verified}; copied {copied}; pending {pending}.")
