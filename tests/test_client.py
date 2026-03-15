"""
Integration tests for the TornadoClient using respx for HTTP mocking.

These tests verify that the client correctly serializes requests,
deserializes responses, and raises appropriate exceptions for error codes.
No real API calls are made — all HTTP traffic is intercepted by respx.
"""

import pytest
import httpx
import respx

from tornado_sdk import TornadoClient, InlineStorageConfig
from tornado_sdk.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from tornado_sdk.models import JobStatus


# Base URL must match the client's default to intercept requests correctly
BASE_URL = "https://api.tornadoapi.io"


@pytest.fixture
def client():
    """Create a test client with retries disabled for predictable error testing."""
    return TornadoClient(api_key="test-key", max_retries=0)


@pytest.fixture
def bearer_client():
    """Create a test client using Bearer token auth (Apify/marketplace mode)."""
    return TornadoClient(api_key="apify_api_test123", auth_mode="bearer", max_retries=0)


# =============================================================================
# Job endpoint tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_create_job(client):
    """POST /jobs should return the job_id from the response."""
    respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(201, json={"job_id": "abc-123"})
    )
    job_id = await client.create_job("https://youtube.com/watch?v=abc")
    assert job_id == "abc-123"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_create_job_batch_response(client):
    """POST /jobs with a Spotify show URL should return the batch_id."""
    respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(
            201,
            json={
                "batch_id": "batch-1",
                "total_episodes": 10,
                "episode_jobs": ["j1", "j2"],
            },
        )
    )
    result = await client.create_job("https://open.spotify.com/show/xxx")
    assert result == "batch-1"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_get_job(client):
    """GET /jobs/:id should return a deserialized Job object."""
    respx.get(f"{BASE_URL}/jobs/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "abc-123",
                "url": "https://youtube.com/watch?v=abc",
                "status": "Completed",
                "s3_url": "https://s3.example.com/video.mp4",
            },
        )
    )
    job = await client.get_job("abc-123")
    assert job.id == "abc-123"
    assert job.status == JobStatus.COMPLETED
    assert job.s3_url == "https://s3.example.com/video.mp4"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_list_jobs(client):
    """GET /jobs should return a list of Job objects and total count."""
    respx.get(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": "j1", "url": "u1", "status": "Completed"},
                    {"id": "j2", "url": "u2", "status": "Pending"},
                ],
                "total": 50,
                "limit": 10,
                "offset": 0,
            },
        )
    )
    jobs, total = await client.list_jobs(limit=10)
    assert len(jobs) == 2
    assert total == 50
    assert jobs[0].id == "j1"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_cancel_job(client):
    """DELETE /jobs/:id should return cancellation confirmation."""
    respx.delete(f"{BASE_URL}/jobs/abc-123").mock(
        return_value=httpx.Response(200, json={"status": "cancelled"})
    )
    result = await client.cancel_job("abc-123")
    assert result["status"] == "cancelled"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_retry_job(client):
    """POST /jobs/:id/retry should return retry confirmation."""
    respx.post(f"{BASE_URL}/jobs/abc-123/retry").mock(
        return_value=httpx.Response(200, json={"status": "retrying"})
    )
    result = await client.retry_job("abc-123")
    assert result["status"] == "retrying"
    await client.close()


# =============================================================================
# Metadata endpoint tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_get_metadata(client):
    """POST /metadata should return a deserialized MetadataResponse."""
    respx.post(f"{BASE_URL}/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Test Video",
                "duration": 120.5,
                "width": 1920,
                "height": 1080,
            },
        )
    )
    meta = await client.get_metadata("https://youtube.com/watch?v=abc")
    assert meta.title == "Test Video"
    assert meta.duration == 120.5
    await client.close()


# =============================================================================
# Usage endpoint tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_get_usage(client):
    """GET /usage should return a deserialized UsageResponse."""
    respx.get(f"{BASE_URL}/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "client_name": "test",
                "usage_count": 100,
                "storage_usage_gb": 5.5,
            },
        )
    )
    usage = await client.get_usage()
    assert usage.client_name == "test"
    assert usage.usage_count == 100
    await client.close()


# =============================================================================
# Batch endpoint tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_get_batch(client):
    """GET /batch/:id should return a deserialized BatchJob."""
    respx.get(f"{BASE_URL}/batch/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "b1",
                "show_url": "https://spotify.com/show/x",
                "status": "processing",
                "total_episodes": 20,
                "completed_episodes": 10,
                "failed_episodes": 1,
                "episode_jobs": ["j1"],
            },
        )
    )
    batch = await client.get_batch("b1")
    assert batch.id == "b1"
    assert batch.total_episodes == 20
    assert batch.completed_episodes == 10
    await client.close()


# =============================================================================
# Bulk jobs endpoint tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_bulk_jobs(client):
    """POST /jobs/bulk should accept URL strings and return batch info."""
    respx.post(f"{BASE_URL}/jobs/bulk").mock(
        return_value=httpx.Response(
            201,
            json={
                "batch_id": "bulk-1",
                "total_jobs": 3,
                "job_ids": ["j1", "j2", "j3"],
            },
        )
    )
    result = await client.create_bulk_jobs(
        ["https://youtube.com/watch?v=1", "https://youtube.com/watch?v=2", "https://youtube.com/watch?v=3"],
        folder="test",
    )
    assert result["total_jobs"] == 3
    assert len(result["job_ids"]) == 3
    await client.close()


# =============================================================================
# Error handling tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_auth_error(client):
    """401 response should raise AuthenticationError with correct status code."""
    respx.get(f"{BASE_URL}/jobs/x").mock(
        return_value=httpx.Response(401, json={"error": "Invalid API Key"})
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await client.get_job("x")
    assert exc_info.value.status_code == 401
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_not_found_error(client):
    """404 response should raise NotFoundError."""
    respx.get(f"{BASE_URL}/jobs/missing").mock(
        return_value=httpx.Response(404, json={"error": "Job not found"})
    )
    with pytest.raises(NotFoundError):
        await client.get_job("missing")
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_validation_error(client):
    """400 response should raise ValidationError."""
    respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(400, json={"error": "Invalid URL"})
    )
    with pytest.raises(ValidationError):
        await client.create_job("not-a-url")
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_error(client):
    """429 response should raise RateLimitError with retry_after from headers."""
    respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(
            429,
            json={"error": "Rate limited"},
            headers={"Retry-After": "30"},
        )
    )
    with pytest.raises(RateLimitError) as exc_info:
        await client.create_job("https://youtube.com/watch?v=abc")
    assert exc_info.value.retry_after == 30
    await client.close()


# =============================================================================
# Bearer token auth tests (Apify/marketplace)
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_bearer_auth_sends_authorization_header(bearer_client):
    """Bearer auth mode should send Authorization header instead of x-api-key."""
    route = respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(201, json={"job_id": "bearer-job-1"})
    )
    job_id = await bearer_client.create_job(
        "https://youtube.com/watch?v=abc",
        storage=InlineStorageConfig.s3(
            endpoint="https://s3.amazonaws.com",
            bucket="test",
            region="us-east-1",
            access_key="AK",
            secret_key="SK",
        ),
    )
    assert job_id == "bearer-job-1"
    # Verify the Authorization header was sent
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer apify_api_test123"
    assert "x-api-key" not in request.headers
    await bearer_client.close()


@respx.mock
@pytest.mark.asyncio
async def test_api_key_auth_sends_x_api_key_header(client):
    """Default api_key mode should send x-api-key header, not Authorization."""
    route = respx.post(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(201, json={"job_id": "key-job-1"})
    )
    await client.create_job("https://youtube.com/watch?v=abc")
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "test-key"
    assert "Authorization" not in request.headers
    await client.close()


def test_invalid_auth_mode_raises():
    """Creating a client with an invalid auth_mode should raise ValueError."""
    import pytest as pt
    with pt.raises(ValueError, match="auth_mode must be"):
        TornadoClient(api_key="x", auth_mode="oauth")


# =============================================================================
# Storage configuration tests
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_configure_s3(client):
    """POST /user/s3 should accept S3StorageConfig and return confirmation."""
    from tornado_sdk import S3StorageConfig

    respx.post(f"{BASE_URL}/user/s3").mock(
        return_value=httpx.Response(
            200,
            json={"message": "OK", "provider": "s3", "container_or_bucket": "test"},
        )
    )
    result = await client.configure_s3(
        S3StorageConfig(
            endpoint="https://s3.amazonaws.com",
            bucket="test",
            region="us-east-1",
            access_key="AK",
            secret_key="SK",
        )
    )
    assert result["provider"] == "s3"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_configure_slack(client):
    """POST /user/slack should accept SlackWebhookConfig and return confirmation."""
    from tornado_sdk import SlackWebhookConfig

    respx.post(f"{BASE_URL}/user/slack").mock(
        return_value=httpx.Response(200, json={"message": "Slack configured"})
    )
    result = await client.configure_slack(
        SlackWebhookConfig(
            webhook_url="https://hooks.slack.com/services/T/B/X",
            notify_level="all",
        )
    )
    assert "message" in result
    await client.close()
