"""
Unit tests for Tornado SDK data models.

Tests serialization (to_dict), deserialization (from_dict), default value
handling, and property accessors for all model classes.
"""

from tornado_sdk.models import (
    BatchJob,
    BlobStorageConfig,
    BulkJobItem,
    CreateBulkRequest,
    CreateJobRequest,
    GcsStorageConfig,
    GDriveStorageConfig,
    InlineStorageConfig,
    IsShortResponse,
    Job,
    JobStatus,
    MetadataResponse,
    OssStorageConfig,
    S3StorageConfig,
    UsageResponse,
)

# =============================================================================
# CreateJobRequest tests
# =============================================================================


def test_create_job_request_minimal():
    """Minimal request should only contain the URL field."""
    req = CreateJobRequest(url="https://youtube.com/watch?v=abc")
    d = req.to_dict()
    assert d == {"url": "https://youtube.com/watch?v=abc"}


def test_create_job_request_full():
    """Full request should serialize all provided parameters."""
    req = CreateJobRequest(
        url="https://youtube.com/watch?v=abc",
        format="mp4",
        video_codec="h264",
        audio_codec="aac",
        audio_bitrate="192k",
        video_quality=23,
        filename="my-video",
        folder="downloads",
        audio_only=True,
        download_subtitles=True,
        max_resolution="1080",
        clip_start="00:01:00",
        clip_end="00:05:00",
    )
    d = req.to_dict()
    assert d["url"] == "https://youtube.com/watch?v=abc"
    assert d["format"] == "mp4"
    assert d["video_codec"] == "h264"
    assert d["audio_only"] is True
    assert d["clip_start"] == "00:01:00"
    assert d["max_resolution"] == "1080"


def test_create_job_request_defaults_omitted():
    """Default-valued fields should NOT appear in the serialized payload."""
    req = CreateJobRequest(url="https://youtube.com/watch?v=abc")
    d = req.to_dict()
    # Boolean defaults (False) should be omitted
    assert "audio_only" not in d
    # None values should be omitted
    assert "format" not in d
    assert "webhook_url" not in d


# =============================================================================
# CreateBulkRequest tests
# =============================================================================


def test_bulk_request():
    """Bulk request should serialize job items and shared options."""
    req = CreateBulkRequest(
        jobs=[
            BulkJobItem(url="https://youtube.com/watch?v=1"),
            BulkJobItem(url="https://youtube.com/watch?v=2", filename="video-2"),
        ],
        folder="my-batch",
        format="mp4",
    )
    d = req.to_dict()
    assert len(d["jobs"]) == 2
    # First job: only URL (no filename)
    assert d["jobs"][0] == {"url": "https://youtube.com/watch?v=1"}
    # Second job: URL + custom filename
    assert d["jobs"][1] == {"url": "https://youtube.com/watch?v=2", "filename": "video-2"}
    assert d["folder"] == "my-batch"


# =============================================================================
# Job response tests
# =============================================================================


def test_job_from_dict():
    """Job should deserialize correctly with all fields mapped."""
    data = {
        "id": "abc-123",
        "url": "https://youtube.com/watch?v=abc",
        "status": "Completed",
        "s3_url": "https://s3.example.com/video.mp4",
        "total_duration_ms": 5000,
        "file_size": 1024000,
    }
    job = Job.from_dict(data)
    assert job.id == "abc-123"
    assert job.status == JobStatus.COMPLETED
    assert job.is_completed
    assert job.is_terminal
    assert not job.is_failed
    assert job.s3_url == "https://s3.example.com/video.mp4"
    assert job.total_duration_ms == 5000


def test_job_statuses():
    """All real API status values should parse correctly."""
    for status_val in ["Pending", "Processing", "Completed", "Failed", "Warning", "Skipped", "Cancelled"]:
        job = Job.from_dict({"id": "x", "url": "u", "status": status_val})
        assert job.status == JobStatus(status_val)


def test_job_warning_and_skipped_are_terminal():
    """Warning and Skipped are real terminal outcomes (regression for the wait_for_job hang)."""
    warning = Job.from_dict({"id": "x", "url": "u", "status": "Warning"})
    assert warning.is_warning
    assert warning.is_terminal
    assert not warning.is_completed

    skipped = Job.from_dict({"id": "x", "url": "u", "status": "Skipped"})
    assert skipped.is_skipped
    assert skipped.is_terminal


def test_job_processing_is_non_terminal():
    """Processing must map to PROCESSING (not PENDING) and stay non-terminal."""
    job = Job.from_dict({"id": "x", "url": "u", "status": "Processing"})
    assert job.status == JobStatus.PROCESSING
    assert not job.is_terminal


def test_job_unknown_status_maps_to_sentinel_and_preserves_raw():
    """Unknown statuses map to UNKNOWN (not PENDING) and keep the raw value, non-terminal."""
    job = Job.from_dict({"id": "x", "url": "u", "status": "SomethingNew"})
    assert job.status == JobStatus.UNKNOWN
    assert job.raw_status == "SomethingNew"
    # Non-terminal so a wait loop keeps polling rather than declaring a wrong outcome.
    assert not job.is_terminal


# =============================================================================
# BatchJob response tests
# =============================================================================


def test_batch_job():
    """BatchJob should deserialize and compute progress correctly."""
    data = {
        "id": "batch-1",
        "show_url": "https://open.spotify.com/show/xxx",
        "status": "processing",
        "folder": "podcast",
        "total_episodes": 100,
        "completed_episodes": 50,
        "failed_episodes": 5,
        "episode_jobs": ["j1", "j2"],
    }
    batch = BatchJob.from_dict(data)
    assert batch.id == "batch-1"
    assert batch.total_episodes == 100
    # 55 out of 100 episodes are done (50 completed + 5 failed)
    assert abs(batch.progress_percent - 55.0) < 0.01
    assert not batch.is_completed
    assert not batch.is_terminal  # status "processing" is still running


def test_batch_finished_is_terminal_not_completed():
    """'finished' = done with some failures: terminal, but not 'completed'."""
    batch = BatchJob.from_dict({
        "id": "b", "show_url": "s", "status": "finished",
        "total_episodes": 3, "completed_episodes": 2, "failed_episodes": 1,
    })
    assert batch.is_finished
    assert batch.is_terminal
    assert not batch.is_completed


# =============================================================================
# MetadataResponse tests
# =============================================================================


def test_metadata_response():
    """MetadataResponse should map all fields from the API response."""
    data = {
        "title": "Test Video",
        "duration": 213.5,
        "width": 1920,
        "height": 1080,
        "extractor": "YouTube",
    }
    meta = MetadataResponse.from_dict(data)
    assert meta.title == "Test Video"
    assert meta.duration == 213.5
    assert meta.width == 1920


# =============================================================================
# UsageResponse tests
# =============================================================================


def test_usage_response():
    """UsageResponse should map usage stats including optional limit fields."""
    data = {
        "client_name": "test-app",
        "usage_count": 500,
        "storage_usage_gb": 12.5,
        "storage_limit_gb": 100.0,
    }
    usage = UsageResponse.from_dict(data)
    assert usage.client_name == "test-app"
    assert usage.usage_count == 500
    assert usage.storage_limit_gb == 100.0


# =============================================================================
# Storage config tests
# =============================================================================


def test_s3_storage_config():
    """S3 config should serialize required fields and optional base_folder."""
    config = S3StorageConfig(
        endpoint="https://s3.amazonaws.com",
        bucket="my-bucket",
        region="us-east-1",
        access_key="AKIA",
        secret_key="secret",
        base_folder="videos",
    )
    d = config.to_dict()
    assert d["endpoint"] == "https://s3.amazonaws.com"
    assert d["base_folder"] == "videos"
    # folder_prefix was not set, so it should be absent
    assert "folder_prefix" not in d


def test_inline_storage_s3():
    """Inline S3 should produce a flat payload with provider tag (Rust serde format)."""
    config = InlineStorageConfig.s3(
        endpoint="https://s3.amazonaws.com",
        bucket="test",
        region="us-east-1",
        access_key="AK",
        secret_key="SK",
    )
    d = config.to_dict()
    # Rust uses #[serde(tag = "provider", rename_all = "lowercase")]
    # so the JSON is flat: {"provider": "s3", "endpoint": ..., "bucket": ...}
    assert d["provider"] == "s3"
    assert d["bucket"] == "test"
    assert d["endpoint"] == "https://s3.amazonaws.com"
    assert d["access_key"] == "AK"


def test_inline_storage_s3_with_folders():
    """Inline S3 should include folder_prefix and base_folder when set."""
    config = InlineStorageConfig.s3(
        endpoint="https://r2.example.com",
        bucket="videos",
        region="auto",
        access_key="AK",
        secret_key="SK",
        folder_prefix="uploads/",
        base_folder="media",
    )
    d = config.to_dict()
    assert d["folder_prefix"] == "uploads/"
    assert d["base_folder"] == "media"


def test_inline_storage_blob():
    """Inline Blob should produce a flat payload with provider tag."""
    config = InlineStorageConfig.blob(
        account_name="myaccount",
        container="videos",
        account_key="key123",
    )
    d = config.to_dict()
    assert d["provider"] == "blob"
    assert d["account_name"] == "myaccount"
    assert d["container"] == "videos"
    assert d["account_key"] == "key123"


def test_inline_storage_gcs():
    """Inline GCS should produce a flat payload with provider tag."""
    config = InlineStorageConfig.gcs(
        project_id="my-project",
        bucket="my-bucket",
        service_account_json='{"type":"service_account"}',
    )
    d = config.to_dict()
    assert d["provider"] == "gcs"
    assert d["project_id"] == "my-project"


def test_inline_storage_oss():
    """Inline OSS should produce a flat payload with provider tag."""
    config = InlineStorageConfig.oss(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="my-bucket",
        access_key_id="AKID",
        access_key_secret="AKSECRET",
    )
    d = config.to_dict()
    assert d["provider"] == "oss"
    assert d["access_key_id"] == "AKID"


# =============================================================================
# Secret redaction in repr() — credentials must never leak into logs/tracebacks
# =============================================================================


def test_s3_config_repr_redacts_secrets():
    """repr(S3StorageConfig) must not expose access_key/secret_key."""
    cfg = S3StorageConfig(
        endpoint="https://s3", bucket="b", region="r",
        access_key="AKIA_PUBLIC", secret_key="TOPSECRET",
    )
    r = repr(cfg)
    assert "TOPSECRET" not in r
    assert "AKIA_PUBLIC" not in r
    # to_dict() must still carry the real values for the wire.
    assert cfg.to_dict()["secret_key"] == "TOPSECRET"


def test_blob_config_repr_redacts_secrets():
    """repr(BlobStorageConfig) must not expose account_key/sas_token."""
    cfg = BlobStorageConfig(
        account_name="acct", container="c",
        account_key="ACCKEY", sas_token="SASTOKEN",
    )
    r = repr(cfg)
    assert "ACCKEY" not in r
    assert "SASTOKEN" not in r


def test_gcs_config_repr_redacts_service_account_json():
    """repr(GcsStorageConfig) must not expose the service-account private key JSON."""
    cfg = GcsStorageConfig(
        project_id="p", bucket="b",
        service_account_json='{"private_key":"-----BEGIN PRIVATE KEY-----LEAK"}',
    )
    assert "LEAK" not in repr(cfg)


def test_oss_config_repr_redacts_secrets():
    """repr(OssStorageConfig) must not expose access_key_id/access_key_secret."""
    cfg = OssStorageConfig(
        endpoint="https://oss", bucket="b",
        access_key_id="AKID", access_key_secret="AKSECRET",
    )
    r = repr(cfg)
    assert "AKID" not in r
    assert "AKSECRET" not in r


def test_inline_storage_repr_redacts_but_keeps_provider():
    """repr(InlineStorageConfig) redacts secrets yet stays useful (provider visible)."""
    cfg = InlineStorageConfig.s3(
        endpoint="https://s3", bucket="b", region="r",
        access_key="AK", secret_key="INLINE_SECRET",
    )
    r = repr(cfg)
    assert "INLINE_SECRET" not in r
    assert "s3" in r  # provider tag still shown for debuggability
    # The real secret is still serialized for the wire.
    assert cfg.to_dict()["secret_key"] == "INLINE_SECRET"


def test_create_job_request_repr_does_not_leak_inline_storage_secret():
    """A CreateJobRequest carrying inline storage must not transitively dump the secret."""
    req = CreateJobRequest(
        url="https://youtube.com/watch?v=abc",
        storage=InlineStorageConfig.s3(
            endpoint="https://s3", bucket="b", region="r",
            access_key="AK", secret_key="NESTED_SECRET",
        ),
    )
    assert "NESTED_SECRET" not in repr(req)


# =============================================================================
# Cancelled-job detection (the API has no "Cancelled" status)
# =============================================================================


def test_is_cancelled_detects_failed_with_cancelled_step():
    """DELETE /jobs/:id persists Failed + step='Cancelled' — is_cancelled must see it."""
    job = Job.from_dict(
        {
            "id": "x",
            "url": "u",
            "status": "Failed",
            "step": "Cancelled",
            "error": "Job cancelled by user",
        }
    )
    assert job.is_cancelled
    assert job.is_failed  # still a Failed status on the wire
    assert job.is_terminal


def test_is_cancelled_false_for_regular_failure():
    """A normal failure (no Cancelled step) must not be flagged as cancelled."""
    job = Job.from_dict({"id": "x", "url": "u", "status": "Failed", "error": "boom"})
    assert not job.is_cancelled


def test_is_cancelled_forward_compat_with_real_status():
    """If the API ever returns a real 'Cancelled' status, is_cancelled still works."""
    job = Job.from_dict({"id": "x", "url": "u", "status": "Cancelled"})
    assert job.status == JobStatus.CANCELLED
    assert job.is_cancelled


# =============================================================================
# Job response fields added for API parity
# =============================================================================


def test_job_parses_thumbnail_and_webhook_diagnostics():
    """thumbnail_url + webhook_* diagnostics are returned by GET /jobs/:id."""
    job = Job.from_dict(
        {
            "id": "x",
            "url": "u",
            "status": "Completed",
            "thumbnail_url": "https://s3/thumb.jpg",
            "webhook_status": "failed",
            "webhook_attempts": 3,
            "webhook_last_error": "HTTP 500",
            "webhook_response_time_ms": 812,
        }
    )
    assert job.thumbnail_url == "https://s3/thumb.jpg"
    assert job.webhook_status == "failed"
    assert job.webhook_attempts == 3
    assert job.webhook_last_error == "HTTP 500"
    assert job.webhook_response_time_ms == 812


def test_job_s3_key_no_longer_reads_phantom_fallbacks():
    """object_key/key/bucket/provider are never sent by the API — no aliasing."""
    job = Job.from_dict(
        {
            "id": "x",
            "url": "u",
            "status": "Completed",
            "object_key": "videos/a.mp4",
            "bucket": "b",
            "provider": "s3",
        }
    )
    assert job.s3_key is None
    assert job.s3_bucket is None
    assert job.storage_provider is None


# =============================================================================
# BatchJob skipped_episodes (terminal batches can have skips)
# =============================================================================


def test_batch_job_parses_skipped_episodes():
    """skipped_episodes is part of GET /batch/:id and must be deserialized."""
    batch = BatchJob.from_dict(
        {
            "id": "b1",
            "show_url": "https://open.spotify.com/show/x",
            "status": "finished",
            "total_episodes": 10,
            "completed_episodes": 7,
            "failed_episodes": 1,
            "skipped_episodes": 2,
        }
    )
    assert batch.skipped_episodes == 2
    assert batch.done_episodes == 10
    assert batch.progress_percent == 100.0
    assert batch.is_terminal


def test_batch_progress_counts_skipped_episodes():
    """A batch with only skips in-flight must not under-report progress."""
    batch = BatchJob.from_dict(
        {
            "id": "b1",
            "show_url": "u",
            "status": "processing",
            "total_episodes": 4,
            "completed_episodes": 1,
            "failed_episodes": 1,
            "skipped_episodes": 1,
        }
    )
    assert batch.done_episodes == 3
    assert batch.progress_percent == 75.0


def test_batch_skipped_defaults_to_zero():
    """Older payloads without skipped_episodes still deserialize."""
    batch = BatchJob.from_dict({"id": "b1", "show_url": "u", "status": "processing"})
    assert batch.skipped_episodes == 0


# =============================================================================
# IsShortResponse (POST /is-short)
# =============================================================================


def test_is_short_response_from_dict():
    resp = IsShortResponse.from_dict(
        {
            "is_short": True,
            "video_type": "short",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": 1.778,
            "duration_seconds": 45,
        }
    )
    assert resp.is_short
    assert resp.video_type == "short"
    assert resp.width == 1080
    assert resp.height == 1920
    assert resp.aspect_ratio == 1.778
    assert resp.duration_seconds == 45


def test_is_short_response_defaults():
    resp = IsShortResponse.from_dict({})
    assert not resp.is_short
    assert resp.video_type == "video"
    assert resp.duration_seconds == 0


# =============================================================================
# GDriveStorageConfig (POST /user/gdrive)
# =============================================================================


def test_gdrive_config_to_dict():
    """folder_id is always sent (empty string = service account root)."""
    cfg = GDriveStorageConfig(
        service_account_json='{"type": "service_account"}',
        folder_id="1AbC",
        folder_prefix="podcasts/",
    )
    d = cfg.to_dict()
    assert d["service_account_json"] == '{"type": "service_account"}'
    assert d["folder_id"] == "1AbC"
    assert d["folder_prefix"] == "podcasts/"
    assert "base_folder" not in d


def test_gdrive_config_defaults_and_redaction():
    cfg = GDriveStorageConfig(service_account_json='{"private_key": "SECRET_PEM"}')
    assert cfg.to_dict()["folder_id"] == ""
    assert "SECRET_PEM" not in repr(cfg)


# =============================================================================
# BlobStorageConfig apply_to_all_keys (org-wide default storage)
# =============================================================================


def test_blob_config_apply_to_all_keys_omitted_by_default():
    cfg = BlobStorageConfig(account_name="acct", container="c", account_key="k")
    assert "apply_to_all_keys" not in cfg.to_dict()


def test_blob_config_apply_to_all_keys_serialized_when_true():
    cfg = BlobStorageConfig(
        account_name="acct", container="c", sas_token="tok", apply_to_all_keys=True
    )
    assert cfg.to_dict()["apply_to_all_keys"] is True
