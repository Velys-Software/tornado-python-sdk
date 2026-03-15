"""
Synchronous usage examples for the Tornado SDK.

All sync methods are prefixed with ``sync_``. They block the current thread
and are ideal for scripts, CLI tools, or environments without an event loop.
"""

from tornado_sdk import TornadoClient

# Initialize the client
client = TornadoClient(api_key="your-api-key-here")

# Create a download job (blocks until the API responds)
job_id = client.sync_create_job(
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    max_resolution="720",
)
print(f"Job created: {job_id}")

# Wait for the job to complete (polls every 2s, 5 minute timeout)
job = client.sync_wait_for_job(job_id, timeout=300)
print(f"Done! URL: {job.s3_url}")

# Extract metadata without downloading
meta = client.sync_get_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
print(f"Title: {meta.title}, Duration: {meta.duration}s")
