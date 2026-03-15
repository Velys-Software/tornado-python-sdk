"""
Basic usage examples for the Tornado SDK.

Demonstrates the most common operations: creating a job, waiting for
completion, audio extraction, video clipping, metadata, and listing jobs.
"""

import asyncio

from tornado_sdk import TornadoClient


async def main():
    # Initialize the client with your API key
    client = TornadoClient(api_key="your-api-key-here")

    # -- 1. Download a YouTube video at 1080p in MP4 format --
    job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        max_resolution="1080",
        format="mp4",
    )
    print(f"Job created: {job_id}")

    # -- 2. Wait for the download to complete (polls every 2s) --
    job = await client.wait_for_job(job_id, timeout=300)
    print(f"Status: {job.status.value}")
    if job.is_completed:
        print(f"Download URL: {job.s3_url}")
        print(f"Total time: {job.total_duration_ms}ms")

    # -- 3. Extract audio only as MP3 at 320kbps --
    audio_job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        audio_only=True,
        audio_codec="mp3",
        audio_bitrate="320k",
        format="mp3",
    )
    print(f"Audio job: {audio_job_id}")

    # -- 4. Clip a 1-minute segment (00:30 to 01:30) --
    clip_job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        clip_start="00:00:30",
        clip_end="00:01:30",
        filename="my-clip",
    )
    print(f"Clip job: {clip_job_id}")

    # -- 5. Get video metadata without downloading --
    metadata = await client.get_metadata(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    print(f"Title: {metadata.title}")
    print(f"Duration: {metadata.duration}s")
    print(f"Resolution: {metadata.width}x{metadata.height}")

    # -- 6. Check your API usage stats --
    usage = await client.get_usage()
    print(f"Jobs used: {usage.usage_count}")
    print(f"Storage: {usage.storage_usage_gb:.2f} GB")

    # -- 7. List your 10 most recent jobs --
    jobs, total = await client.list_jobs(limit=10)
    print(f"Total jobs: {total}")
    for j in jobs:
        print(f"  {j.id} - {j.status.value} - {j.title}")

    # Always close the client to release HTTP connections
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
