"""
Tornado SDK - Official Python client for the Tornado Video Downloader API.

This package provides a high-performance async/sync client for downloading
videos from YouTube, Spotify, and other platforms via the Tornado API.
Downloads are uploaded to your own cloud storage (S3, Azure Blob, GCS, OSS).

Quick Start:
    >>> from tornado_sdk import TornadoClient
    >>> client = TornadoClient(api_key="your-key")
    >>> job_id = client.sync_create_job("https://youtube.com/watch?v=...")
    >>> job = client.sync_wait_for_job(job_id)
    >>> print(job.s3_url)

For async usage:
    >>> async with TornadoClient(api_key="your-key") as client:
    ...     job_id = await client.create_job("https://youtube.com/watch?v=...")
    ...     job = await client.wait_for_job(job_id)
"""

# -- Main client class --------------------------------------------------------
from tornado_sdk.client import TornadoClient

# -- Data models (request/response types) ------------------------------------
from tornado_sdk.models import (
    Job,
    JobStatus,
    CreateJobRequest,
    CreateBulkRequest,
    BulkJobItem,
    BatchJob,
    MetadataResponse,
    UsageResponse,
    # Storage configuration models for each cloud provider
    S3StorageConfig,
    BlobStorageConfig,
    GcsStorageConfig,
    OssStorageConfig,
    SlackWebhookConfig,
    # Inline storage credentials passed per-job (marketplace users)
    InlineStorageConfig,
)

# -- Exception hierarchy ------------------------------------------------------
from tornado_sdk.exceptions import (
    TornadoError,        # Base exception for all SDK errors
    TornadoAPIError,     # HTTP error returned by the API (has status_code)
    AuthenticationError, # 401/403 - invalid or missing API key
    RateLimitError,      # 429 - rate limit exceeded (has retry_after)
    NotFoundError,       # 404 - job/batch/resource not found
    ValidationError,     # 400 - invalid request parameters
)

__version__ = "1.0.0"

# Public API surface - everything importable via `from tornado_sdk import *`
__all__ = [
    # Client
    "TornadoClient",
    # Models
    "Job",
    "JobStatus",
    "CreateJobRequest",
    "CreateBulkRequest",
    "BulkJobItem",
    "BatchJob",
    "MetadataResponse",
    "UsageResponse",
    # Storage configs
    "S3StorageConfig",
    "BlobStorageConfig",
    "GcsStorageConfig",
    "OssStorageConfig",
    "SlackWebhookConfig",
    "InlineStorageConfig",
    # Exceptions
    "TornadoError",
    "TornadoAPIError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
]
