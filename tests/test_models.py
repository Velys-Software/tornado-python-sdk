"""
Unit tests for Tornado SDK data models.

Tests serialization (to_dict), deserialization (from_dict), default value
handling, and property accessors for all model classes.
"""

from tornado_sdk.models import (
    CreateJobRequest,
    CreateBulkRequest,
    BulkJobItem,
    Job,
    JobStatus,
    BatchJob,
    MetadataResponse,
    UsageResponse,
    S3StorageConfig,
    InlineStorageConfig,
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
    """All known status values should parse correctly."""
    for status_val in ["Pending", "Downloading", "Muxing", "Uploading", "Completed", "Failed", "Cancelled"]:
        job = Job.from_dict({"id": "x", "url": "u", "status": status_val})
        assert job.status == JobStatus(status_val)


def test_job_unknown_status_defaults():
    """Unknown status values from a newer API version should default to Pending."""
    job = Job.from_dict({"id": "x", "url": "u", "status": "SomethingNew"})
    assert job.status == JobStatus.PENDING


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
