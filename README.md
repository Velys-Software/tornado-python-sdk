# Tornado Python SDK — YouTube Video Downloader API & Spotify Podcast Downloader

[![PyPI version](https://img.shields.io/pypi/v/tornado-sdk)](https://pypi.org/project/tornado-sdk/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

The official Python SDK for the [Tornado Video Downloader API](https://tornadoapi.io/) — the industrial-grade API to **download YouTube videos**, **Spotify podcasts**, and content from dozens of platforms at scale, with **direct cloud delivery** to S3, Azure Blob, GCS, Cloudflare R2, and more.

Built on a purpose-built extraction engine written in Rust (not a yt-dlp wrapper), Tornado delivers a **99.998% extraction success rate**, sub-minute job completion, and scales from 100 to 100,000+ videos/day without code changes.

> **100 GB free proof-of-concept included.** No credit card required. First download in under 5 minutes.
>
> [Get your API key](https://accounts.dash.tornadoapi.io/) | [Full API Documentation](https://docs.tornadoapi.io/) | [Tornado Homepage](https://tornadoapi.io/)

## Why Tornado API?

| | yt-dlp + proxies | Tornado API |
|---|---|---|
| **Reliability** | Breaks every 2 weeks | 99.998% success rate |
| **Scale** | Manual infra management | 100 to 100,000+ videos/day |
| **Blocking** | Constant 403 errors | Zero blocked requests |
| **Storage** | Download locally, then upload | Direct-to-cloud delivery (zero egress fees) |
| **Maintenance** | You maintain everything | Fully managed API — one HTTP call |
| **Speed** | Sequential, slow | 600-1000 videos/hour, sub-minute completion |

## Installation

```bash
pip install tornado-sdk
```

Requires Python 3.10+. The only dependency is [`httpx`](https://www.python-httpx.org/).

## Quick Start — Download YouTube Videos with Python

### Async (recommended for high throughput)

```python
import asyncio
from tornado_sdk import TornadoClient

async def main():
    client = TornadoClient(api_key="your-api-key")

    # Download a YouTube video directly to your S3 bucket
    job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        max_resolution="1080",
        format="mp4",
    )

    # Wait for completion — file is uploaded directly to your cloud storage
    job = await client.wait_for_job(job_id, timeout=300)
    print(f"Download URL: {job.s3_url}")

    await client.close()

asyncio.run(main())
```

### Synchronous

```python
from tornado_sdk import TornadoClient

client = TornadoClient(api_key="your-api-key")
job_id = client.sync_create_job("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
job = client.sync_wait_for_job(job_id, timeout=300)
print(f"Download URL: {job.s3_url}")
```

> [Sign up free](https://accounts.dash.tornadoapi.io/) to get your API key.

## Features

- **Async + Sync** — Both async and synchronous APIs for any use case
- **YouTube Video Downloader** — Download YouTube videos, Shorts, playlists, and live streams up to 4K/8K
- **Spotify Podcast Downloader** — Batch download entire Spotify shows and episodes
- **Bulk Downloads** — Up to 100 videos per API call, no rate limits
- **Direct Cloud Delivery** — Files stream directly to S3, Azure Blob, GCS, Cloudflare R2, DigitalOcean Spaces, Backblaze B2, Wasabi, MinIO, or any S3-compatible storage
- **Zero Egress Fees** — No intermediate hops, no bandwidth surcharges
- **Audio Extraction** — Download audio only in M4A, MP3, OGG, or Opus
- **Video Clipping** — Clip segments with start/end timestamps
- **Live Stream Recording** — Record YouTube and Twitch live streams
- **Subtitle Downloads** — Extract subtitles alongside video files
- **Metadata Extraction** — Get video info (title, duration, resolution) without downloading
- **Auto-Retry** — Automatic retry with exponential backoff on rate limits (429) and server errors (5xx)
- **Type-Safe** — Full type hints and dataclass models
- **Webhooks** — Completion, progress, and failure notifications
- **Slack Notifications** — Get alerted on job failures via Slack webhooks

## Supported Platforms

YouTube (videos, Shorts, playlists, live streams) • Spotify (episodes, full shows) • TikTok • Instagram • Twitter/X • Facebook • and [dozens more](https://docs.tornadoapi.io/)

## Supported Cloud Storage Providers

AWS S3 • Cloudflare R2 • Azure Blob Storage • Google Cloud Storage (GCS) • Alibaba OSS • DigitalOcean Spaces • Backblaze B2 • Wasabi • MinIO • OVH Object Storage • Any S3-compatible endpoint

## API Reference

### Download YouTube Videos (Single Job)

```python
# Create a download job with full control over format, codec, and quality
job_id = await client.create_job(
    url="https://youtube.com/watch?v=...",
    format="mp4",              # mp4, mkv, webm, mov, mp3, m4a, ogg, opus
    video_codec="copy",        # copy, h264, h265, vp9
    audio_codec="aac",         # copy, aac, opus, mp3
    audio_bitrate="192k",      # 64k, 128k, 192k, 256k, 320k
    video_quality=23,          # CRF 0-51 (lower = better quality)
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
    live_from_start=False,     # Record from beginning of live stream
    max_duration=3600,         # Max duration in seconds
    wait_for_video=False,      # Wait for scheduled/upcoming streams
    webhook_url="https://...", # Completion webhook
    enable_progress_webhook=False,
)

# Get job status
job = await client.get_job(job_id)

# Wait for completion with polling
job = await client.wait_for_job(job_id, poll_interval=2.0, timeout=300)

# List all jobs with filtering
jobs, total = await client.list_jobs(limit=10, offset=0, status="Completed")

# Cancel / Retry / Delete file
await client.cancel_job(job_id)
await client.retry_job(job_id)
await client.delete_job_file(job_id)
```

### Bulk YouTube Video Downloads

Download up to 100 videos in a single API call — no rate limits, no blocked requests.

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

### Spotify Podcast Downloader (Batch)

Download entire Spotify shows with episode rename support.

```python
# Spotify shows automatically create batches with all episodes
batch_id = await client.create_job(
    "https://open.spotify.com/show/...",
    folder="my-podcast",
    paused=True,  # Create paused to rename episodes first
)

# Rename episodes before downloading
await client.rename_batch_jobs(batch_id, [
    {"job_id": "...", "filename": "Episode 1 - Title"},
])

# Start the batch download
await client.start_batch(batch_id)

# Monitor progress
batch = await client.wait_for_batch(batch_id, timeout=3600)
print(f"{batch.completed_episodes}/{batch.total_episodes} done")
```

### Video Metadata Extraction

Get video info without downloading — useful for validation, previews, and building UIs.

```python
meta = await client.get_metadata("https://youtube.com/watch?v=...")
print(f"Title: {meta.title}")
print(f"Duration: {meta.duration}s")
print(f"Resolution: {meta.width}x{meta.height}")
```

### Cloud Storage Configuration (S3, Azure, GCS, R2)

```python
from tornado_sdk import S3StorageConfig, BlobStorageConfig, InlineStorageConfig

# Configure account-level S3 / Cloudflare R2 storage
await client.configure_s3(S3StorageConfig(
    endpoint="https://account.r2.cloudflarestorage.com",
    bucket="my-videos",
    region="auto",
    access_key="...",
    secret_key="...",
))

# Or pass inline storage credentials per-job (for marketplace users)
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

### Usage & Quota Monitoring

```python
usage = await client.get_usage()
print(f"Jobs: {usage.usage_count}")
print(f"Storage: {usage.storage_usage_gb:.2f} GB")
```

## Error Handling

```python
from tornado_sdk.exceptions import (
    AuthenticationError,  # 401/403 — invalid or missing API key
    RateLimitError,       # 429 — rate limit exceeded (has retry_after)
    NotFoundError,        # 404 — job/batch not found
    ValidationError,      # 400 — invalid request parameters
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

## Authentication

```python
# Direct API users (default) — uses x-api-key header
client = TornadoClient(api_key="sk_your_api_key")

# Marketplace users (Apify, RapidAPI, Zyla) — uses Bearer token
client = TornadoClient(api_key="your_token", auth_mode="bearer")
```

## Use Cases

- **Video Clipping Platforms** — Clip and deliver YouTube segments at scale
- **Podcast Analytics** — Download and analyze Spotify podcast episodes
- **Content Repurposing** — Download videos for social media redistribution
- **AI Training Datasets** — Build multimodal datasets from YouTube and podcast content
- **Media Archival** — Archive video content directly to cloud storage

## Links

- [Tornado API Homepage](https://tornadoapi.io/)
- [API Documentation](https://docs.tornadoapi.io/)
- [Sign Up / Dashboard](https://accounts.dash.tornadoapi.io/)
- [Swagger Interactive Docs](https://api.tornadoapi.io/swagger)

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE) for details.
