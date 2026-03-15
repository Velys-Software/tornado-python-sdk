"""
Data models for the Tornado SDK.

All models are Python dataclasses with full type annotations. Each model
provides a ``to_dict()`` method for serialization (request models) or a
``from_dict()`` class method for deserialization (response models).

Models are grouped into:
    - Request models: CreateJobRequest, CreateBulkRequest, BulkJobItem
    - Response models: Job, BatchJob, MetadataResponse, UsageResponse
    - Storage configs: S3StorageConfig, BlobStorageConfig, GcsStorageConfig,
      OssStorageConfig, SlackWebhookConfig, InlineStorageConfig
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# =============================================================================
# Enumerations
# =============================================================================


class JobStatus(str, Enum):
    """Possible states of a download job in the pipeline.

    Lifecycle: Pending -> Downloading -> Muxing -> Uploading -> Completed
    A job can transition to Failed or Cancelled from any active state.
    """

    PENDING = "Pending"           # Queued, waiting for a worker to pick it up
    DOWNLOADING = "Downloading"   # Worker is downloading video/audio streams
    MUXING = "Muxing"             # FFmpeg is muxing audio+video into final container
    UPLOADING = "Uploading"       # Uploading the final file to cloud storage
    COMPLETED = "Completed"       # Done - s3_url is available
    FAILED = "Failed"             # Failed - check error and error_type fields
    CANCELLED = "Cancelled"       # Cancelled by user via DELETE /jobs/:id


# =============================================================================
# Request Models
# =============================================================================


@dataclass
class CreateJobRequest:
    """Parameters for creating a single download job via POST /jobs.

    Only ``url`` is required. All other parameters are optional and have
    sensible defaults on the server side.

    Args:
        url: Video URL to download (YouTube, Spotify, TikTok, Instagram, etc.)
        webhook_url: URL to receive POST webhook on completion/failure.
        format: Output container format: mp4, mkv, webm, mov, mp3, m4a, ogg, opus.
            Default: mp4 (or m4a for audio_only).
        video_codec: Video codec: copy, h264, h265, vp9.
            Default: copy (no re-encoding, fastest).
        audio_codec: Audio codec: copy, aac, opus, mp3.
            Default: copy (falls back to aac if incompatible with container).
        audio_bitrate: Audio bitrate: 64k, 128k, 192k, 256k, 320k.
            Default: copy original bitrate (or 192k if transcoding).
        video_quality: Video quality CRF value (0-51, lower = better quality).
            Only used when video_codec is not "copy". Default: 23.
        filename: Custom filename for the output file (without extension).
        folder: S3 folder prefix for organizing uploads (e.g., "podcasts/2024").
        audio_only: Extract audio track only (no video). Default: False.
        download_subtitles: Download subtitles if available. Default: False.
        download_thumbnail: Download video thumbnail image. Default: False.
        quality_preset: Quality preset overriding video_quality:
            "highest", "high", "medium", "low", "lowest".
        max_resolution: Maximum video resolution cap:
            "best", "2160", "1440", "1080", "720", "480", "360". Default: "best".
        clip_start: Start timestamp for clipping (format: "HH:MM:SS" or seconds "120").
        clip_end: End timestamp for clipping (format: "HH:MM:SS" or seconds "300").
        live_recording: Enable live stream recording mode. Default: False.
        live_from_start: For live streams, record from the beginning. Default: False.
        max_duration: Safety cap for recording duration in seconds (e.g., 3600 = 1h).
        wait_for_video: Wait for scheduled/upcoming streams to go live. Default: False.
        enable_progress_webhook: Send progress updates every ~10% or 5s. Default: False.
        storage: Inline storage credentials for this specific job.
            Used by marketplace users (RapidAPI, Apify) who provide their own storage.
        paused: For Spotify show batches: create in paused mode so you can rename
            episodes before starting downloads. Default: False.
    """

    url: str
    webhook_url: Optional[str] = None
    format: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_bitrate: Optional[str] = None
    video_quality: Optional[int] = None
    filename: Optional[str] = None
    folder: Optional[str] = None
    audio_only: bool = False
    download_subtitles: bool = False
    download_thumbnail: bool = False
    quality_preset: Optional[str] = None
    max_resolution: Optional[str] = None
    clip_start: Optional[str] = None
    clip_end: Optional[str] = None
    live_recording: bool = False
    live_from_start: bool = False
    max_duration: Optional[int] = None
    wait_for_video: bool = False
    enable_progress_webhook: bool = False
    storage: Optional[InlineStorageConfig] = None
    paused: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API request payload, omitting None and default-False values.

        The API uses serde(default) on the Rust side, so omitting a field
        is equivalent to sending the default value. This keeps payloads minimal.
        """
        d: dict[str, Any] = {"url": self.url}

        # Optional string/int fields: only include if explicitly set
        if self.webhook_url is not None:
            d["webhook_url"] = self.webhook_url
        if self.format is not None:
            d["format"] = self.format
        if self.video_codec is not None:
            d["video_codec"] = self.video_codec
        if self.audio_codec is not None:
            d["audio_codec"] = self.audio_codec
        if self.audio_bitrate is not None:
            d["audio_bitrate"] = self.audio_bitrate
        if self.video_quality is not None:
            d["video_quality"] = self.video_quality
        if self.filename is not None:
            d["filename"] = self.filename
        if self.folder is not None:
            d["folder"] = self.folder

        # Boolean fields: only include when True (server defaults to false)
        if self.audio_only:
            d["audio_only"] = True
        if self.download_subtitles:
            d["download_subtitles"] = True
        if self.download_thumbnail:
            d["download_thumbnail"] = True

        # Quality/resolution controls
        if self.quality_preset is not None:
            d["quality_preset"] = self.quality_preset
        if self.max_resolution is not None:
            d["max_resolution"] = self.max_resolution

        # Clipping parameters
        if self.clip_start is not None:
            d["clip_start"] = self.clip_start
        if self.clip_end is not None:
            d["clip_end"] = self.clip_end

        # Live stream parameters
        if self.live_recording:
            d["live_recording"] = True
        if self.live_from_start:
            d["live_from_start"] = True
        if self.max_duration is not None:
            d["max_duration"] = self.max_duration
        if self.wait_for_video:
            d["wait_for_video"] = True

        # Webhook progress updates
        if self.enable_progress_webhook:
            d["enable_progress_webhook"] = True

        # Inline storage credentials (marketplace users)
        if self.storage is not None:
            d["storage"] = self.storage.to_dict()

        # Paused batch mode (Spotify shows only)
        if self.paused:
            d["paused"] = True

        return d


@dataclass
class BulkJobItem:
    """A single item in a bulk job request (POST /jobs/bulk).

    Args:
        url: Video URL to download.
        filename: Optional custom filename for this specific job.
            If not provided, the video title is used.
    """

    url: str
    filename: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload."""
        d: dict[str, Any] = {"url": self.url}
        if self.filename is not None:
            d["filename"] = self.filename
        return d


@dataclass
class CreateBulkRequest:
    """Parameters for creating multiple download jobs at once via POST /jobs/bulk.

    Maximum 100 jobs per request. All jobs share the same encoding options
    but can have individual filenames via BulkJobItem.

    Args:
        jobs: List of BulkJobItem with URLs and optional filenames.
        folder: Shared S3 folder prefix for all jobs in the batch.
        format: Output container format for all jobs.
        video_codec: Video codec for all jobs.
        audio_codec: Audio codec for all jobs.
        audio_bitrate: Audio bitrate for all jobs.
        video_quality: Video quality CRF for all jobs.
        audio_only: Audio-only mode for all jobs. Default: False.
        download_subtitles: Download subtitles for all jobs. Default: False.
        download_thumbnail: Download thumbnails for all jobs. Default: False.
        quality_preset: Quality preset for all jobs.
        max_resolution: Max resolution cap for all jobs.
        clip_start: Clip start timestamp for all jobs.
        clip_end: Clip end timestamp for all jobs.
        live_recording: Live recording mode for all jobs. Default: False.
        live_from_start: Record from stream beginning for all jobs. Default: False.
        max_duration: Max recording duration for all jobs (seconds).
        wait_for_video: Wait for scheduled streams for all jobs. Default: False.
    """

    jobs: list[BulkJobItem]
    folder: Optional[str] = None
    format: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_bitrate: Optional[str] = None
    video_quality: Optional[int] = None
    audio_only: bool = False
    download_subtitles: bool = False
    download_thumbnail: bool = False
    quality_preset: Optional[str] = None
    max_resolution: Optional[str] = None
    clip_start: Optional[str] = None
    clip_end: Optional[str] = None
    live_recording: bool = False
    live_from_start: bool = False
    max_duration: Optional[int] = None
    wait_for_video: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload. Same omission logic as CreateJobRequest."""
        d: dict[str, Any] = {"jobs": [j.to_dict() for j in self.jobs]}

        # Shared encoding options
        if self.folder is not None:
            d["folder"] = self.folder
        if self.format is not None:
            d["format"] = self.format
        if self.video_codec is not None:
            d["video_codec"] = self.video_codec
        if self.audio_codec is not None:
            d["audio_codec"] = self.audio_codec
        if self.audio_bitrate is not None:
            d["audio_bitrate"] = self.audio_bitrate
        if self.video_quality is not None:
            d["video_quality"] = self.video_quality
        if self.audio_only:
            d["audio_only"] = True
        if self.download_subtitles:
            d["download_subtitles"] = True
        if self.download_thumbnail:
            d["download_thumbnail"] = True
        if self.quality_preset is not None:
            d["quality_preset"] = self.quality_preset
        if self.max_resolution is not None:
            d["max_resolution"] = self.max_resolution
        if self.clip_start is not None:
            d["clip_start"] = self.clip_start
        if self.clip_end is not None:
            d["clip_end"] = self.clip_end
        if self.live_recording:
            d["live_recording"] = True
        if self.live_from_start:
            d["live_from_start"] = True
        if self.max_duration is not None:
            d["max_duration"] = self.max_duration
        if self.wait_for_video:
            d["wait_for_video"] = True

        return d


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class Job:
    """Represents a download job returned by GET /jobs/:id or GET /jobs.

    Contains the job's current status, output URLs, performance metrics,
    and the original request parameters echoed back for reference.

    Key properties:
        - ``is_completed``: True if status == Completed
        - ``is_failed``: True if status == Failed
        - ``is_terminal``: True if the job won't change state anymore
        - ``s3_url``: Download URL for the output file (available when completed)
    """

    # -- Core fields (always present) -----------------------------------------
    id: str                                  # Unique job UUID
    url: str                                 # Original video URL
    status: JobStatus                        # Current pipeline stage

    # -- Output fields (populated on completion) ------------------------------
    s3_url: Optional[str] = None             # Presigned download URL for the output file
    subtitle_url: Optional[str] = None       # Presigned URL for subtitle file (if requested)
    error: Optional[str] = None              # Error message (if failed)
    error_type: Optional[str] = None         # "error" for technical, "warning" for content issues
    step: Optional[str] = None               # Current pipeline step description
    title: Optional[str] = None              # Video title extracted from source

    # -- Performance metrics (populated progressively) ------------------------
    download_speed_mbps: Optional[float] = None    # Download speed in Mbps
    upload_speed_mbps: Optional[float] = None      # Upload speed to storage in Mbps
    extract_duration_ms: Optional[int] = None      # Time to extract stream info
    download_duration_ms: Optional[int] = None     # Time to download streams
    mux_duration_ms: Optional[int] = None          # Time for FFmpeg muxing
    upload_duration_ms: Optional[int] = None       # Time to upload to storage
    total_duration_ms: Optional[int] = None        # Total wall-clock time
    precheck_duration_ms: Optional[int] = None     # YouTube API pre-check time
    io_wait_ms: Optional[int] = None               # Time waiting for IO semaphore
    cpu_wait_ms: Optional[int] = None              # Time waiting for CPU semaphore
    upload_wait_ms: Optional[int] = None           # Time waiting for upload semaphore
    download_strategy: Optional[str] = None        # Which download method was used
    cascade_total_attempts: Optional[int] = None   # Total cascade fallback attempts
    subtitle_duration_ms: Optional[int] = None     # Time to download subtitles
    file_move_ms: Optional[int] = None             # Time to move temp files
    file_size: Optional[int] = None                # Output file size in bytes
    native_video_codec: Optional[str] = None       # Original video codec from source
    native_audio_codec: Optional[str] = None       # Original audio codec from source
    download_retries: Optional[int] = None         # Number of download retry attempts
    upload_retries: Optional[int] = None           # Number of upload retry attempts
    queue_wait_ms: Optional[int] = None            # Time spent waiting in queue
    requested_quality: Optional[str] = None        # Quality that was requested
    actual_quality: Optional[str] = None           # Quality that was actually downloaded
    webhook_status: Optional[str] = None           # Webhook delivery status
    created_at: Optional[int] = None               # Job creation timestamp (epoch ms)
    finished_at: Optional[int] = None              # Job completion timestamp (epoch ms)

    # -- User-provided parameters echoed back ---------------------------------
    description: Optional[str] = None              # Spotify episode description
    release_date: Optional[str] = None             # Spotify episode release date
    folder: Optional[str] = None                   # S3 folder prefix
    batch_id: Optional[str] = None                 # Parent batch ID (if part of bulk/batch)
    format: Optional[str] = None                   # Requested output format
    video_codec: Optional[str] = None              # Requested video codec
    audio_codec: Optional[str] = None              # Requested audio codec
    audio_bitrate: Optional[str] = None            # Requested audio bitrate
    video_quality: Optional[int] = None            # Requested CRF value
    filename: Optional[str] = None                 # Custom filename
    audio_only: Optional[bool] = None              # Audio-only mode
    download_subtitles: Optional[bool] = None      # Subtitles requested
    download_thumbnail: Optional[bool] = None      # Thumbnail requested
    quality_preset: Optional[str] = None           # Quality preset used
    max_resolution: Optional[str] = None           # Resolution cap
    clip_start: Optional[str] = None               # Clip start timestamp
    clip_end: Optional[str] = None                 # Clip end timestamp
    live_recording: Optional[bool] = None          # Live recording mode
    live_from_start: Optional[bool] = None         # Record from beginning
    max_duration: Optional[int] = None             # Duration cap in seconds
    wait_for_video: Optional[bool] = None          # Wait for scheduled stream
    enable_progress_webhook: Optional[bool] = None # Progress webhooks enabled
    marketplace_source: Optional[str] = None       # Marketplace origin (RapidAPI, Apify, etc.)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Deserialize a job from the API JSON response.

        Handles unknown status values gracefully by defaulting to PENDING.
        """
        status_str = data.get("status", "Pending")
        try:
            status = JobStatus(status_str)
        except ValueError:
            # Unknown status value from a newer API version - default to Pending
            status = JobStatus.PENDING

        return cls(
            id=data["id"],
            url=data.get("url", ""),
            status=status,
            s3_url=data.get("s3_url"),
            subtitle_url=data.get("subtitle_url"),
            error=data.get("error"),
            error_type=data.get("error_type"),
            step=data.get("step"),
            title=data.get("title"),
            download_speed_mbps=data.get("download_speed_mbps"),
            upload_speed_mbps=data.get("upload_speed_mbps"),
            extract_duration_ms=data.get("extract_duration_ms"),
            download_duration_ms=data.get("download_duration_ms"),
            mux_duration_ms=data.get("mux_duration_ms"),
            upload_duration_ms=data.get("upload_duration_ms"),
            total_duration_ms=data.get("total_duration_ms"),
            precheck_duration_ms=data.get("precheck_duration_ms"),
            io_wait_ms=data.get("io_wait_ms"),
            cpu_wait_ms=data.get("cpu_wait_ms"),
            upload_wait_ms=data.get("upload_wait_ms"),
            download_strategy=data.get("download_strategy"),
            cascade_total_attempts=data.get("cascade_total_attempts"),
            subtitle_duration_ms=data.get("subtitle_duration_ms"),
            file_move_ms=data.get("file_move_ms"),
            file_size=data.get("file_size"),
            native_video_codec=data.get("native_video_codec"),
            native_audio_codec=data.get("native_audio_codec"),
            download_retries=data.get("download_retries"),
            upload_retries=data.get("upload_retries"),
            queue_wait_ms=data.get("queue_wait_ms"),
            requested_quality=data.get("requested_quality"),
            actual_quality=data.get("actual_quality"),
            webhook_status=data.get("webhook_status"),
            created_at=data.get("created_at"),
            finished_at=data.get("finished_at"),
            description=data.get("description"),
            release_date=data.get("release_date"),
            folder=data.get("folder"),
            batch_id=data.get("batch_id"),
            format=data.get("format"),
            video_codec=data.get("video_codec"),
            audio_codec=data.get("audio_codec"),
            audio_bitrate=data.get("audio_bitrate"),
            video_quality=data.get("video_quality"),
            filename=data.get("filename"),
            audio_only=data.get("audio_only"),
            download_subtitles=data.get("download_subtitles"),
            download_thumbnail=data.get("download_thumbnail"),
            quality_preset=data.get("quality_preset"),
            max_resolution=data.get("max_resolution"),
            clip_start=data.get("clip_start"),
            clip_end=data.get("clip_end"),
            live_recording=data.get("live_recording"),
            live_from_start=data.get("live_from_start"),
            max_duration=data.get("max_duration"),
            wait_for_video=data.get("wait_for_video"),
            enable_progress_webhook=data.get("enable_progress_webhook"),
            marketplace_source=data.get("marketplace_source"),
        )

    @property
    def is_completed(self) -> bool:
        """True if the job finished successfully and s3_url is available."""
        return self.status == JobStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """True if the job failed. Check ``error`` for details."""
        return self.status == JobStatus.FAILED

    @property
    def is_cancelled(self) -> bool:
        """True if the job was cancelled by the user."""
        return self.status == JobStatus.CANCELLED

    @property
    def is_terminal(self) -> bool:
        """True if the job is in a final state and will not change anymore."""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass
class BatchJob:
    """Represents a batch download returned by GET /batch/:id.

    Batches are created automatically when submitting a Spotify show URL,
    or manually via POST /jobs/bulk. Each batch contains multiple episode jobs.
    """

    id: str                                        # Batch UUID
    show_url: str                                  # Original Spotify show URL
    status: str                                    # Batch status: "paused", "processing", "completed"
    folder: Optional[str] = None                   # S3 folder prefix for all episodes
    total_episodes: int = 0                        # Total number of episodes in the batch
    completed_episodes: int = 0                    # Episodes that finished successfully
    failed_episodes: int = 0                       # Episodes that failed
    episode_jobs: list[str] = field(default_factory=list)  # List of individual job UUIDs

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchJob:
        """Deserialize a batch from the API JSON response."""
        return cls(
            id=data["id"],
            show_url=data.get("show_url", ""),
            status=data.get("status", "unknown"),
            folder=data.get("folder"),
            total_episodes=data.get("total_episodes", 0),
            completed_episodes=data.get("completed_episodes", 0),
            failed_episodes=data.get("failed_episodes", 0),
            episode_jobs=data.get("episode_jobs", []),
        )

    @property
    def is_completed(self) -> bool:
        """True if the batch status is 'completed'."""
        return self.status == "completed"

    @property
    def progress_percent(self) -> float:
        """Overall batch progress as a percentage (0.0 - 100.0).

        Includes both completed and failed episodes in the numerator,
        since failed episodes are also "done" from a progress perspective.
        """
        if self.total_episodes == 0:
            return 0.0
        return (self.completed_episodes + self.failed_episodes) / self.total_episodes * 100


@dataclass
class MetadataResponse:
    """Video metadata extracted via POST /metadata without downloading.

    Useful for previewing video info, validating URLs, or building
    a UI before submitting download jobs.
    """

    title: Optional[str] = None           # Video title
    duration: Optional[float] = None      # Duration in seconds
    width: Optional[int] = None           # Video width in pixels
    height: Optional[int] = None          # Video height in pixels
    extractor: Optional[str] = None       # Platform name (e.g., "YouTube", "TikTok")
    uploader: Optional[str] = None        # Channel or uploader name
    thumbnail: Optional[str] = None       # Thumbnail image URL
    description: Optional[str] = None     # Video description text
    view_count: Optional[int] = None      # Total view count
    like_count: Optional[int] = None      # Total like count
    upload_date: Optional[str] = None     # Upload date in YYYYMMDD format
    filesize_approx: Optional[int] = None # Approximate file size in bytes

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetadataResponse:
        """Deserialize metadata from the API JSON response."""
        return cls(
            title=data.get("title"),
            duration=data.get("duration"),
            width=data.get("width"),
            height=data.get("height"),
            extractor=data.get("extractor"),
            uploader=data.get("uploader"),
            thumbnail=data.get("thumbnail"),
            description=data.get("description"),
            view_count=data.get("view_count"),
            like_count=data.get("like_count"),
            upload_date=data.get("upload_date"),
            filesize_approx=data.get("filesize_approx"),
        )


@dataclass
class UsageResponse:
    """API usage statistics returned by GET /usage.

    Includes storage consumption, billing period info, and per-key limits.
    """

    client_name: str                                    # Name associated with the API key
    usage_count: int                                    # Total number of jobs created
    storage_usage_gb: float                             # Total storage used in GB
    storage_reserved_gb: Optional[float] = None         # Storage reserved by in-progress jobs
    storage_effective_usage_gb: Optional[float] = None  # Used + reserved storage
    storage_limit_gb: Optional[float] = None            # Storage quota in GB (if limited)
    storage_limit_bytes: Optional[int] = None           # Storage quota in bytes
    storage_remaining_gb: Optional[float] = None        # Remaining storage quota
    billing_period_start: Optional[int] = None          # Billing period start (epoch timestamp)
    billing_period_end: Optional[int] = None            # Billing period end (epoch timestamp)
    current_period_usage_gb: Optional[float] = None     # Usage in current billing period
    max_resolution_limit: Optional[str] = None          # Resolution cap on this key (e.g., "720")
    max_duration_limit_seconds: Optional[int] = None    # Duration cap on this key (seconds)
    max_filesize_limit_bytes: Optional[int] = None      # File size cap on this key (bytes)
    max_filesize_limit_mb: Optional[float] = None       # File size cap in MB

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageResponse:
        """Deserialize usage stats from the API JSON response."""
        return cls(
            client_name=data.get("client_name", ""),
            usage_count=data.get("usage_count", 0),
            storage_usage_gb=data.get("storage_usage_gb", 0.0),
            storage_reserved_gb=data.get("storage_reserved_gb"),
            storage_effective_usage_gb=data.get("storage_effective_usage_gb"),
            storage_limit_gb=data.get("storage_limit_gb"),
            storage_limit_bytes=data.get("storage_limit_bytes"),
            storage_remaining_gb=data.get("storage_remaining_gb"),
            billing_period_start=data.get("billing_period_start"),
            billing_period_end=data.get("billing_period_end"),
            current_period_usage_gb=data.get("current_period_usage_gb"),
            max_resolution_limit=data.get("max_resolution_limit"),
            max_duration_limit_seconds=data.get("max_duration_limit_seconds"),
            max_filesize_limit_bytes=data.get("max_filesize_limit_bytes"),
            max_filesize_limit_mb=data.get("max_filesize_limit_mb"),
        )


# =============================================================================
# Storage Configuration Models
# =============================================================================
# These models represent account-level storage settings configured via
# POST /user/s3, /user/blob, /user/gcs, /user/oss endpoints.
# Once configured, all subsequent jobs use this storage automatically.


@dataclass
class S3StorageConfig:
    """S3-compatible storage configuration (AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces).

    Configured via POST /user/s3. Credentials are validated before saving.

    Args:
        endpoint: S3 endpoint URL (e.g., "https://s3.amazonaws.com" or R2 endpoint).
        bucket: Bucket name to upload files to.
        region: AWS region (e.g., "us-east-1") or "auto" for Cloudflare R2.
        access_key: AWS Access Key ID.
        secret_key: AWS Secret Access Key.
        folder_prefix: Optional folder prefix for all uploads (e.g., "videos/").
        base_folder: Base folder for organizing uploads (default: "videos").
    """

    endpoint: str
    bucket: str
    region: str
    access_key: str
    secret_key: str
    folder_prefix: Optional[str] = None
    base_folder: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload, omitting optional None fields."""
        d: dict[str, Any] = {
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "region": self.region,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
        }
        if self.folder_prefix is not None:
            d["folder_prefix"] = self.folder_prefix
        if self.base_folder is not None:
            d["base_folder"] = self.base_folder
        return d


@dataclass
class BlobStorageConfig:
    """Azure Blob Storage configuration.

    Configured via POST /user/blob. Provide either account_key or sas_token
    (mutually exclusive).

    Args:
        account_name: Azure Storage account name.
        container: Blob container name.
        account_key: Storage account key (mutually exclusive with sas_token).
        sas_token: SAS token for scoped access (mutually exclusive with account_key).
        folder_prefix: Optional folder prefix for all uploads.
        base_folder: Base folder for organizing uploads (default: "videos").
    """

    account_name: str
    container: str
    account_key: Optional[str] = None
    sas_token: Optional[str] = None
    folder_prefix: Optional[str] = None
    base_folder: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload."""
        d: dict[str, Any] = {
            "account_name": self.account_name,
            "container": self.container,
        }
        if self.account_key is not None:
            d["account_key"] = self.account_key
        if self.sas_token is not None:
            d["sas_token"] = self.sas_token
        if self.folder_prefix is not None:
            d["folder_prefix"] = self.folder_prefix
        if self.base_folder is not None:
            d["base_folder"] = self.base_folder
        return d


@dataclass
class GcsStorageConfig:
    """Google Cloud Storage configuration.

    Configured via POST /user/gcs.

    Args:
        project_id: GCP project ID.
        bucket: GCS bucket name.
        service_account_json: Full service account JSON key file content as a string.
        folder_prefix: Optional folder prefix for all uploads.
        base_folder: Base folder for organizing uploads (default: "videos").
    """

    project_id: str
    bucket: str
    service_account_json: str
    folder_prefix: Optional[str] = None
    base_folder: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload."""
        d: dict[str, Any] = {
            "project_id": self.project_id,
            "bucket": self.bucket,
            "service_account_json": self.service_account_json,
        }
        if self.folder_prefix is not None:
            d["folder_prefix"] = self.folder_prefix
        if self.base_folder is not None:
            d["base_folder"] = self.base_folder
        return d


@dataclass
class OssStorageConfig:
    """Alibaba Cloud OSS configuration.

    Configured via POST /user/oss.

    Args:
        endpoint: OSS endpoint (e.g., "https://oss-cn-hangzhou.aliyuncs.com").
        bucket: OSS bucket name.
        access_key_id: Alibaba Cloud Access Key ID.
        access_key_secret: Alibaba Cloud Access Key Secret.
        folder_prefix: Optional folder prefix for all uploads.
        base_folder: Base folder for organizing uploads (default: "videos").
    """

    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    folder_prefix: Optional[str] = None
    base_folder: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload."""
        d: dict[str, Any] = {
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "access_key_id": self.access_key_id,
            "access_key_secret": self.access_key_secret,
        }
        if self.folder_prefix is not None:
            d["folder_prefix"] = self.folder_prefix
        if self.base_folder is not None:
            d["base_folder"] = self.base_folder
        return d


@dataclass
class SlackWebhookConfig:
    """Slack webhook notification configuration.

    Configured via POST /user/slack. Sends alerts when jobs fail or
    encounter warnings (private videos, bot detection, etc.).

    Args:
        webhook_url: Slack incoming webhook URL
            (must start with "https://hooks.slack.com/services/").
        notify_level: Notification level:
            "all" (errors + warnings), "errors_only", "warnings_only".
            Default: "all".
    """

    webhook_url: str
    notify_level: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API payload."""
        d: dict[str, Any] = {"webhook_url": self.webhook_url}
        if self.notify_level is not None:
            d["notify_level"] = self.notify_level
        return d


# =============================================================================
# Inline Storage (per-job credentials)
# =============================================================================


@dataclass
class InlineStorageConfig:
    """Inline storage credentials passed directly in a job creation request.

    This is used by marketplace users (RapidAPI, Apify, Zyla) who provide
    their own storage credentials per-job, or by direct API users who want
    to override their account-level storage for a specific job.

    The Rust API deserializes this as an internally-tagged enum:
    ``#[serde(tag = "provider", rename_all = "lowercase")]``, so the JSON
    format is flat with a ``"provider"`` discriminator field:

        {"provider": "s3", "endpoint": "...", "bucket": "...", ...}

    Use one of the factory class methods to create an instance:

        >>> storage = InlineStorageConfig.s3(endpoint=..., bucket=..., ...)
        >>> storage = InlineStorageConfig.blob(account_name=..., container=..., ...)
        >>> storage = InlineStorageConfig.gcs(project_id=..., bucket=..., ...)
        >>> storage = InlineStorageConfig.oss(endpoint=..., bucket=..., ...)
    """

    _data: dict[str, Any] = field(default_factory=dict)  # Flat payload with "provider" tag

    @classmethod
    def s3(
        cls,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        folder_prefix: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> InlineStorageConfig:
        """Create an inline S3-compatible storage config.

        Args:
            endpoint: S3 endpoint URL.
            bucket: Bucket name.
            region: AWS region or "auto" for R2.
            access_key: Access Key ID.
            secret_key: Secret Access Key.
            folder_prefix: Optional folder prefix.
            base_folder: Base folder (default: "videos").
        """
        # Flat structure with "provider" tag — matches Rust serde(tag = "provider")
        data: dict[str, Any] = {
            "provider": "s3",
            "endpoint": endpoint,
            "bucket": bucket,
            "region": region,
            "access_key": access_key,
            "secret_key": secret_key,
        }
        if folder_prefix is not None:
            data["folder_prefix"] = folder_prefix
        if base_folder is not None:
            data["base_folder"] = base_folder
        return cls(_data=data)

    @classmethod
    def blob(
        cls,
        account_name: str,
        container: str,
        account_key: Optional[str] = None,
        sas_token: Optional[str] = None,
        folder_prefix: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> InlineStorageConfig:
        """Create an inline Azure Blob Storage config.

        Args:
            account_name: Azure Storage account name.
            container: Blob container name.
            account_key: Account key (mutually exclusive with sas_token).
            sas_token: SAS token (mutually exclusive with account_key).
            folder_prefix: Optional folder prefix.
            base_folder: Base folder (default: "videos").
        """
        data: dict[str, Any] = {
            "provider": "blob",
            "account_name": account_name,
            "container": container,
        }
        if account_key is not None:
            data["account_key"] = account_key
        if sas_token is not None:
            data["sas_token"] = sas_token
        if folder_prefix is not None:
            data["folder_prefix"] = folder_prefix
        if base_folder is not None:
            data["base_folder"] = base_folder
        return cls(_data=data)

    @classmethod
    def gcs(
        cls,
        project_id: str,
        bucket: str,
        service_account_json: str,
        folder_prefix: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> InlineStorageConfig:
        """Create an inline Google Cloud Storage config.

        Args:
            project_id: GCP project ID.
            bucket: GCS bucket name.
            service_account_json: Service account JSON key as string.
            folder_prefix: Optional folder prefix.
            base_folder: Base folder (default: "videos").
        """
        data: dict[str, Any] = {
            "provider": "gcs",
            "project_id": project_id,
            "bucket": bucket,
            "service_account_json": service_account_json,
        }
        if folder_prefix is not None:
            data["folder_prefix"] = folder_prefix
        if base_folder is not None:
            data["base_folder"] = base_folder
        return cls(_data=data)

    @classmethod
    def oss(
        cls,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        folder_prefix: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> InlineStorageConfig:
        """Create an inline Alibaba Cloud OSS config.

        Args:
            endpoint: OSS endpoint URL.
            bucket: OSS bucket name.
            access_key_id: Alibaba Access Key ID.
            access_key_secret: Alibaba Access Key Secret.
            folder_prefix: Optional folder prefix.
            base_folder: Base folder (default: "videos").
        """
        data: dict[str, Any] = {
            "provider": "oss",
            "endpoint": endpoint,
            "bucket": bucket,
            "access_key_id": access_key_id,
            "access_key_secret": access_key_secret,
        }
        if folder_prefix is not None:
            data["folder_prefix"] = folder_prefix
        if base_folder is not None:
            data["base_folder"] = base_folder
        return cls(_data=data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to flat API payload with ``"provider"`` discriminator tag.

        Matches Rust's ``#[serde(tag = "provider", rename_all = "lowercase")]``.
        """
        return self._data
