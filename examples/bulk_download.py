"""
Bulk download example — fan out many YouTube downloads concurrently.

For plain video URLs (YouTube, TikTok, ...), use ``bulk_youtube_jobs()``: it
issues one ``POST /jobs`` per URL under a concurrency limit and returns normal
job IDs that work with ``get_job()`` / ``wait_for_job()``.

Note: the server-side ``create_bulk_jobs()`` (``POST /jobs/bulk``) is designed
for Spotify show batches. For non-Spotify URLs the IDs it returns are NOT
addressable via ``get_job()`` — so don't use it for YouTube.
"""

import asyncio

from tornado_sdk import BulkJobItem, TornadoClient


async def main():
    client = TornadoClient(api_key="your-api-key-here")

    # Mixed input types:
    # - Plain URL strings (filename auto-detected from the video title)
    # - BulkJobItem objects (with a custom filename)
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        BulkJobItem(url="https://www.youtube.com/watch?v=kJQP7kiw5Fk", filename="despacito"),
    ]

    # Fan out create_job() calls (max 8 concurrent), returning addressable job IDs.
    # return_exceptions=True keeps going if some submissions fail, placing the
    # Exception at the same index instead of aborting the whole batch.
    job_ids = await client.bulk_youtube_jobs(
        urls,
        concurrency=8,
        return_exceptions=True,
        folder="my-playlist",     # All files stored under this S3 prefix
        max_resolution="1080",
        format="mp4",
    )

    # Wait for each successfully-created job and report results.
    # bulk_youtube_jobs returns one result per input, in order, so lengths match.
    for source, job_id in zip(urls, job_ids, strict=True):
        label = source.url if isinstance(source, BulkJobItem) else source
        if isinstance(job_id, Exception):
            print(f"  {label}: SUBMIT FAILED: {job_id}")
            continue
        job = await client.wait_for_job(job_id, timeout=600)
        status = "OK" if job.is_completed else f"FAIL: {job.error}"
        print(f"  {job_id}: {status}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
