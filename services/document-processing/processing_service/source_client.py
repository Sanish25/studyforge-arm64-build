"""Authenticated, bounded retrieval of a source document from Django."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from botocore.exceptions import BotoCoreError, ClientError

from .object_storage import client as object_client
from .errors import DocumentDeletedError, PermanentProcessingError, ProcessingError, RetryableProcessingError

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_BYTES = MAX_PDF_BYTES
SOURCE_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
SOURCE_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class SourceDocument:
    content: bytes
    mime_type: str


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def fetch_source_pdf(job_id: int, document_id: int, source_sha256: str) -> bytes:
    """Compatibility entry point for existing PDF callers."""
    source = fetch_source_document(job_id, document_id, source_sha256)
    if source.mime_type != "application/pdf":
        raise PermanentProcessingError("Django returned a non-PDF source.")
    return source.content


def fetch_source_document(job_id: int, document_id: int, source_sha256: str) -> SourceDocument:
    """Fetch a correlated source over the authenticated internal Django endpoint."""
    if not isinstance(job_id, int) or isinstance(job_id, bool) or job_id <= 0:
        raise PermanentProcessingError("job_id must be a positive integer.")
    if not isinstance(document_id, int) or isinstance(document_id, bool) or document_id <= 0:
        raise PermanentProcessingError("document_id must be a positive integer.")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256 or ""):
        raise PermanentProcessingError("source_sha256 must be a lowercase SHA-256 digest.")

    base_url = str(getattr(settings, "PROCESSING_DJANGO_API_URL", "") or "").strip()
    token = str(getattr(settings, "PROCESSING_SERVICE_TOKEN", "") or "").strip()
    if not base_url:
        raise PermanentProcessingError("PROCESSING_DJANGO_API_URL is not configured.")
    if not token:
        raise PermanentProcessingError("PROCESSING_SERVICE_TOKEN is not configured.")
    if not base_url.startswith(("https://", "http://")):
        raise PermanentProcessingError("PROCESSING_DJANGO_API_URL must use HTTP or HTTPS.")

    if getattr(settings, "PROCESSING_SOURCE_MODE", "django") == "s3":
        return _fetch_object_source(base_url, token, job_id, document_id, source_sha256)

    url = urljoin(
        base_url.rstrip("/") + "/",
        f"internal/v1/jobs/{job_id}/document/",
    )
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": ", ".join(sorted(SOURCE_MIMES)),
        },
        method="GET",
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=SOURCE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise _response_error(response.status)
            mime_type = response.headers.get_content_type()
            if mime_type not in SOURCE_MIMES:
                raise PermanentProcessingError("Django returned an unsupported source format.")
            if response.headers.get("X-Document-ID") != str(document_id):
                raise PermanentProcessingError("Django returned a different document.")
            if response.headers.get("X-Source-SHA256") != source_sha256:
                raise PermanentProcessingError("Django returned a different source digest.")

            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise PermanentProcessingError(
                        "Django returned an invalid source size."
                    ) from exc
                if declared_size < 0:
                    raise PermanentProcessingError("Django returned an invalid source size.")
                if declared_size > MAX_DOCUMENT_BYTES:
                    raise PermanentProcessingError(
                        "The source document exceeds the processing size limit."
                    )
            source_bytes = response.read(MAX_DOCUMENT_BYTES + 1)
    except HTTPError as exc:
        raise _response_error(exc.code) from exc
    except URLError as exc:
        raise RetryableProcessingError("Could not retrieve the source document from Django.") from exc
    except (TimeoutError, OSError) as exc:
        raise RetryableProcessingError("Could not retrieve the source document from Django.") from exc

    if not source_bytes:
        raise PermanentProcessingError("Django returned an empty source document.")
    if len(source_bytes) > MAX_DOCUMENT_BYTES:
        raise PermanentProcessingError("The source document exceeds the processing size limit.")
    if hashlib.sha256(source_bytes).hexdigest() != source_sha256:
        raise PermanentProcessingError("The source document digest does not match the job.")
    return SourceDocument(source_bytes, mime_type)


def _fetch_object_source(base_url, token, job_id, document_id, source_sha256):
    locator_url = urljoin(base_url.rstrip("/") + "/", f"internal/v1/jobs/{job_id}/object/")
    request = Request(locator_url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, method="GET")
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=SOURCE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise _response_error(response.status)
            locator = json.loads(response.read(4096))
    except HTTPError as exc:
        raise _response_error(exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RetryableProcessingError("Could not retrieve the source reference from Django.") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise PermanentProcessingError("Django returned an invalid source reference.") from exc
    if not isinstance(locator, dict) or set(locator) != {"document_id", "source_sha256", "object_key", "mime_type"}:
        raise PermanentProcessingError("Django returned an invalid source reference.")
    key = locator["object_key"]
    mime_type = locator["mime_type"]
    if (locator["document_id"] != document_id or locator["source_sha256"] != source_sha256
        or not isinstance(key, str) or not key.startswith("documents/") or ".." in key.split("/")
        or mime_type not in SOURCE_MIMES):
        raise PermanentProcessingError("Django returned a different or invalid source reference.")
    try:
        result = object_client().get_object(Bucket=settings.PROCESSING_STORAGE_BUCKET, Key=key)
        body = result["Body"]
        try:
            content = body.read(MAX_DOCUMENT_BYTES + 1)
        finally:
            body.close()
    except (BotoCoreError, ClientError, OSError) as exc:
        raise RetryableProcessingError("Could not retrieve the source object.") from exc
    if not content or len(content) > MAX_DOCUMENT_BYTES or hashlib.sha256(content).hexdigest() != source_sha256:
        raise PermanentProcessingError("The source object is invalid or does not match the job.")
    return SourceDocument(content, mime_type)


def _response_error(status: int) -> ProcessingError:
    if status == 404:
        return DocumentDeletedError("Django no longer has this document or job.")
    if status in {408, 429} or status >= 500:
        return RetryableProcessingError(
            f"Django source retrieval failed with HTTP status {status}."
        )
    return PermanentProcessingError(
        f"Django rejected source retrieval with HTTP status {status}."
    )
