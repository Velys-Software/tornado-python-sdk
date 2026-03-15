"""
Bulk download example — download multiple videos in a single API call.

The bulk endpoint accepts up to 100 URLs per request. All jobs share
the same encoding settings but can have individual filenames.
"""

import asyncio

from tornado_sdk import TornadoClient, BulkJobItem


async def main():
    client = TornadoClient(api_key="your-api-key-here")

    # Create bulk jobs with mixed input types:
    # - Plain URL strings (filename auto-detected from video title)
    # - BulkJobItem objects (with custom filename)
    result = await client.create_bulk_jobs(
        jobs=[
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=9bZkp7q19f0",
            BulkJobItem(url="https://www.youtube.com/watch?v=kJQP7kiw5Fk", filename="despacito"),
        ],
        folder="my-playlist",     # All files stored under this S3 prefix
        max_resolution="1080",
        format="mp4",
    )

    print(f"Batch ID: {result['batch_id']}")
    print(f"Created {result['total_jobs']} jobs")

    # Wait for each job individually and report results
    for job_id in result["job_ids"]:
        job = await client.wait_for_job(job_id, timeout=600)
        status = "OK" if job.is_completed else f"FAIL: {job.error}"
        print(f"  {job_id}: {status}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
