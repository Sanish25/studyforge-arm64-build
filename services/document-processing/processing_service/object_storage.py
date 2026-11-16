"""Read-only S3-compatible access for production document workers."""

import boto3
from botocore.config import Config
from django.conf import settings


def client():
    options = {
        "region_name": settings.PROCESSING_STORAGE_REGION,
        "config": Config(
            connect_timeout=settings.PROCESSING_STORAGE_CONNECT_TIMEOUT,
            read_timeout=settings.PROCESSING_STORAGE_READ_TIMEOUT,
            retries={"max_attempts": 2},
            s3={"addressing_style": settings.PROCESSING_STORAGE_ADDRESSING_STYLE},
        ),
    }
    if settings.PROCESSING_STORAGE_ENDPOINT_URL:
        options["endpoint_url"] = settings.PROCESSING_STORAGE_ENDPOINT_URL
    if settings.PROCESSING_STORAGE_ACCESS_KEY_ID:
        options["aws_access_key_id"] = settings.PROCESSING_STORAGE_ACCESS_KEY_ID
        options["aws_secret_access_key"] = settings.PROCESSING_STORAGE_SECRET_ACCESS_KEY
    if settings.PROCESSING_STORAGE_SESSION_TOKEN:
        options["aws_session_token"] = settings.PROCESSING_STORAGE_SESSION_TOKEN
    if settings.PROCESSING_STORAGE_CA_BUNDLE:
        options["verify"] = settings.PROCESSING_STORAGE_CA_BUNDLE
    return boto3.client("s3", **options)
