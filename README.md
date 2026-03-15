# Tornado Python SDK

Python SDK for the [Tornado Video Downloader API](https://docs.tornadoapi.io). Download YouTube, Spotify, and other videos at scale with S3/R2/Azure/GCS storage.

## Installation

```bash
pip install tornado-sdk
```

## Quick Start

### Async (recommended)

```python
import asyncio
from tornado_sdk import TornadoClient

async def main():
    client = TornadoClient(api_key="your-api-key")

    # Download a video
    job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        max_resolution="1080",
        format="mp4",
    )

    # Wait for completion
    job = await client.wait_for_job(job_id, timeout=300)
    print(f"Download URL: {job.s3_url}")

    await client.close()

asyncio.run(main())
```

### Sync

```python
from tornado_sdk import TornadoClient

client = TornadoClient(api_key="your-api-key")
job_id = client.sync_create_job("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
job = client.sync_wait_for_job(job_id, timeout=300)
print(f"Download URL: {job.s3_url}")
```

## Features

- **Async + Sync** - Both async and synchronous APIs
- **Auto-retry** - Automatic retry on rate limits (429) and server errors (5xx)
- **Type-safe** - Full type hints and dataclass models
- **All endpoints** - Jobs, Bulk, Batch (Spotify), Metadata, Storage, Usage
- **Multi-cloud storage** - S3, Azure Blob, GCS, Alibaba OSS

## API Reference

### Jobs

```python
# Create a job with all options
job_id = await client.create_job(
    url="https://youtube.com/watch?v=...",
    format="mp4",              # mp4, mkv, webm, mov, mp3, m4a, ogg, opus
    video_codec="copy",        # copy, h264, h265, vp9
    audio_codec="aac",         # copy, aac, opus, mp3
    audio_bitrate="192k",      # 64k, 128k, 192k, 256k, 320k
    video_quality=23,          # CRF 0-51 (lower=better)
    filename="my-video",       # Custom filename
    folder="downloads",        # S3 folder prefix
    audio_only=False,          # Extract audio only
    download_subtitles=False,  # Download subtitles
    download_thumbnail=False,  # Download thumbnail
    quality_preset="high",     # highest, high, medium, low, lowest
    max_resolution="1080",     # best, 2160, 1440, 1080, 720, 480, 360
    clip_start="00:01:00",     # Clip start timestamp
    clip_end="00:05:00",       # Clip end timestamp
    live_recording=False,      # Live stream recording
    live_from_start=False,     # Record from beginning
    max_duration=3600,         # Max duration (seconds)
    wait_for_video=False,      # Wait for scheduled streams
    webhook_url="https://...", # Completion webhook
    enable_progress_webhook=False,
)

# Get job status
job = await client.get_job(job_id)

# Wait for completion
job = await client.wait_for_job(job_id, poll_interval=2.0, timeout=300)

# List jobs
jobs, total = await client.list_jobs(limit=10, offset=0, status="Completed")

# Cancel / Retry / Delete file
await client.cancel_job(job_id)
await client.retry_job(job_id)
await client.delete_job_file(job_id)
```

### Bulk Downloads

```python
from tornado_sdk import BulkJobItem

result = await client.create_bulk_jobs(
    jobs=[
        "https://youtube.com/watch?v=...",
        BulkJobItem(url="https://youtube.com/watch?v=...", filename="custom-name"),
    ],
    folder="my-playlist",
    max_resolution="1080",
)
# result = {"batch_id": "...", "total_jobs": 2, "job_ids": ["...", "..."]}
```

### Batch (Spotify Shows)

```python
# Spotify shows auto-create batches
batch_id = await client.create_job(
    "https://open.spotify.com/show/...",
    folder="my-podcast",
    paused=True,  # Create paused to rename episodes first
)

# Rename episodes
await client.rename_batch_jobs(batch_id, [
    {"job_id": "...", "filename": "Episode 1 - Title"},
])

# Start the batch
await client.start_batch(batch_id)

# Monitor progress
batch = await client.wait_for_batch(batch_id, timeout=3600)
print(f"{batch.completed_episodes}/{batch.total_episodes} done")
```

### Metadata

```python
meta = await client.get_metadata("https://youtube.com/watch?v=...")
print(f"Title: {meta.title}")
print(f"Duration: {meta.duration}s")
print(f"Resolution: {meta.width}x{meta.height}")
```

### Storage Configuration

```python
from tornado_sdk import S3StorageConfig, BlobStorageConfig, InlineStorageConfig

# Configure account-level S3 storage
await client.configure_s3(S3StorageConfig(
    endpoint="https://account.r2.cloudflarestorage.com",
    bucket="my-videos",
    region="auto",
    access_key="...",
    secret_key="...",
))

# Or pass inline storage per-job
job_id = await client.create_job(
    "https://youtube.com/watch?v=...",
    storage=InlineStorageConfig.s3(
        endpoint="https://s3.amazonaws.com",
        bucket="my-bucket",
        region="us-east-1",
        access_key="...",
        secret_key="...",
    ),
)
```

### Usage

```python
usage = await client.get_usage()
print(f"Jobs: {usage.usage_count}")
print(f"Storage: {usage.storage_usage_gb:.2f} GB")
```

## Error Handling

```python
from tornado_sdk.exceptions import (
    AuthenticationError,  # 401/403
    RateLimitError,       # 429 (has retry_after attribute)
    NotFoundError,        # 404
    ValidationError,      # 400
    TornadoAPIError,      # Other HTTP errors
)

try:
    job = await client.get_job("invalid-id")
except NotFoundError:
    print("Job not found")
except AuthenticationError:
    print("Invalid API key")
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
