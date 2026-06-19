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
async def test_list_jobs_lowercases_status_filter(client):
    """The status filter must be sent lowercase to match the API contract."""
    route = respx.get(f"{BASE_URL}/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": [], "total": 0})
    )
    # Caller passes the PascalCase Job.status value; the client must normalize it.
    await client.list_jobs(status="Completed")
    assert "status=completed" in str(route.calls[0].request.url)
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


@pytest.mark.asyncio
async def test_bulk_jobs_over_100_raises_validation_error(client):
    """create_bulk_jobs must enforce the documented 100-job cap client-side."""
    urls = [f"https://youtube.com/watch?v={i}" for i in range(101)]
    with pytest.raises(ValidationError):
        await client.create_bulk_jobs(urls)
    await client.close()


def test_sync_bulk_jobs_over_100_raises_validation_error():
    """sync_create_bulk_jobs must enforce the same 100-job cap."""
    with TornadoClient(api_key="k", max_retries=0) as c:
        urls = [f"https://youtube.com/watch?v={i}" for i in range(101)]
        with pytest.raises(ValidationError):
            c.sync_create_bulk_jobs(urls)


@respx.mock
@pytest.mark.asyncio
async def test_wait_for_batch_returns_on_finished_status(client, monkeypatch):
    """A 'finished' batch (done, some episodes failed) is terminal — must return, not hang."""
    async def _no_sleep(_seconds: float) -> None:
        return None

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

    respx.get(f"{BASE_URL}/batch/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "b1", "show_url": "s", "status": "finished",
                "total_episodes": 3, "completed_episodes": 2, "failed_episodes": 1,
            },
        )
    )
    batch = await client.wait_for_batch("b1", poll_interval=0.0, timeout=5.0)
    assert batch.is_terminal
    assert batch.is_finished
    assert not batch.is_completed
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
async def test_rate_limit_error(client, monkeypatch):
    """429 with max_retries=0 must raise RateLimitError immediately, WITHOUT sleeping.

    Regression: the 429 branch previously slept the full Retry-After (30s) even
    when no retries remained, blocking the caller and the test suite.
    """
    slept: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _record_sleep)

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
    # max_retries=0 -> fail fast, no sleep at all.
    assert slept == []
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_429_then_success(monkeypatch):
    """A 429 should be retried (within max_retries), honoring Retry-After, then succeed."""
    slept: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _record_sleep)

    c = TornadoClient(api_key="k", max_retries=2)
    respx.post(f"{BASE_URL}/jobs").mock(
        side_effect=[
            httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "1"}),
            httpx.Response(201, json={"job_id": "ok"}),
        ]
    )
    job_id = await c.create_job("https://youtube.com/watch?v=abc")
    assert job_id == "ok"
    assert slept == [1.0]  # honored Retry-After once
    await c.close()


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_500_then_success(monkeypatch):
    """A 5xx should be retried with clamped exponential backoff, then succeed."""
    slept: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _record_sleep)

    c = TornadoClient(api_key="k", max_retries=3)
    respx.get(f"{BASE_URL}/jobs/abc").mock(
        side_effect=[
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(200, json={"id": "abc", "url": "u", "status": "Completed"}),
        ]
    )
    job = await c.get_job("abc")
    assert job.is_completed
    # Exponential backoff now uses full jitter: one sleep in [0, 2**0].
    assert len(slept) == 1
    assert 0.0 <= slept[0] <= 1.0
    await c.close()


@respx.mock
@pytest.mark.asyncio
async def test_exponential_backoff_is_jittered(monkeypatch):
    """The no-Retry-After backoff path must stay within [0, 2**attempt] (jittered)."""
    slept: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _record_sleep)

    c = TornadoClient(api_key="k", max_retries=3)
    respx.get(f"{BASE_URL}/jobs/abc").mock(
        side_effect=[
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(200, json={"id": "abc", "url": "u", "status": "Completed"}),
        ]
    )
    job = await c.get_job("abc")
    assert job.is_completed
    assert len(slept) == 2
    assert 0.0 <= slept[0] <= 1.0   # attempt 0 -> [0, 1]
    assert 0.0 <= slept[1] <= 2.0   # attempt 1 -> [0, 2]
    await c.close()


@respx.mock
@pytest.mark.asyncio
async def test_retry_after_is_clamped_to_max_backoff(monkeypatch):
    """A huge server Retry-After must be clamped to max_backoff (no unbounded block)."""
    slept: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        slept.append(seconds)

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _record_sleep)

    c = TornadoClient(api_key="k", max_retries=1, max_backoff=5.0)
    respx.post(f"{BASE_URL}/jobs").mock(
        side_effect=[
            httpx.Response(429, json={"error": "x"}, headers={"Retry-After": "86400"}),
            httpx.Response(201, json={"job_id": "ok"}),
        ]
    )
    job_id = await c.create_job("https://youtube.com/watch?v=abc")
    assert job_id == "ok"
    assert slept == [5.0]  # clamped from 86400
    await c.close()


@respx.mock
@pytest.mark.asyncio
async def test_wait_for_job_returns_on_warning_status(client, monkeypatch):
    """A Warning job is terminal — wait_for_job must return it, not hang/timeout.

    Critical regression: Warning/Skipped used to deserialize to PENDING, so
    is_terminal stayed False and wait_for_job never returned.
    """
    async def _no_sleep(_seconds: float) -> None:
        return None

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

    respx.get(f"{BASE_URL}/jobs/warn").mock(
        return_value=httpx.Response(
            200, json={"id": "warn", "url": "u", "status": "Warning", "error": "private video"}
        )
    )
    job = await client.wait_for_job("warn", poll_interval=0.0, timeout=5.0)
    assert job.is_terminal
    assert job.is_warning
    await client.close()


@respx.mock
def test_negative_retry_after_does_not_crash_sync():
    """A negative Retry-After must not crash time.sleep in the sync retry path (#8).

    Before the clamp, int('-5') -> time.sleep(-5) raised a raw ValueError that
    escaped the RateLimitError/TornadoAPIError contract.
    """
    c = TornadoClient(api_key="k", max_retries=1)
    with c:
        respx.post(f"{BASE_URL}/jobs").mock(
            side_effect=[
                httpx.Response(429, json={"error": "x"}, headers={"Retry-After": "-5"}),
                httpx.Response(201, json={"job_id": "ok"}),
            ]
        )
        job_id = c.sync_create_job("https://youtube.com/watch?v=abc")
        assert job_id == "ok"


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


# =============================================================================
# Defensive parsing tests (regression for null/empty bodies)
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_success_null_body_does_not_crash(client):
    """A literal JSON `null` on a 200 should be coerced to {} instead of crashing."""
    respx.delete(f"{BASE_URL}/jobs/abc/file").mock(
        return_value=httpx.Response(200, content=b"null", headers={"Content-Type": "application/json"})
    )
    result = await client.delete_job_file("abc")
    assert result == {}
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_success_204_no_content_does_not_crash(client):
    """An empty 204 body should be coerced to {} instead of raising on response.json()."""
    respx.delete(f"{BASE_URL}/jobs/abc/file").mock(
        return_value=httpx.Response(204)
    )
    result = await client.delete_job_file("abc")
    assert result == {}
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_error_null_body_does_not_crash(client):
    """A 500 with literal JSON `null` body must surface as TornadoAPIError, not AttributeError."""
    from tornado_sdk.exceptions import TornadoAPIError

    respx.get(f"{BASE_URL}/jobs/abc").mock(
        return_value=httpx.Response(500, content=b"null", headers={"Content-Type": "application/json"})
    )
    with pytest.raises(TornadoAPIError) as exc_info:
        await client.get_job("abc")
    assert exc_info.value.status_code == 500
    # message falls back to "HTTP 500" when no error key is present
    assert "500" in str(exc_info.value)
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_error_plain_text_body(client):
    """Non-JSON error bodies (e.g. gateway HTML) should surface as TornadoAPIError with the text."""
    from tornado_sdk.exceptions import TornadoAPIError

    respx.get(f"{BASE_URL}/jobs/abc").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )
    with pytest.raises(TornadoAPIError) as exc_info:
        await client.get_job("abc")
    assert exc_info.value.status_code == 502
    assert "Bad Gateway" in str(exc_info.value)
    await client.close()


# =============================================================================
# wait_for_job NotFound grace period (regression for create→read race)
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_wait_for_job_tolerates_transient_404(client, monkeypatch):
    """wait_for_job should poll through a transient 404 within the grace period."""
    # Avoid actually sleeping in tests
    async def _no_sleep(_seconds: float) -> None:
        return None

    import asyncio as _asyncio

    monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

    # First call -> 404, second call -> Completed
    route = respx.get(f"{BASE_URL}/jobs/abc").mock(
        side_effect=[
            httpx.Response(404, json={"error": "Job not found"}),
            httpx.Response(
                200,
                json={"id": "abc", "url": "u", "status": "Completed"},
            ),
        ]
    )
    job = await client.wait_for_job("abc", poll_interval=0.0, not_found_grace_period=10.0)
    assert job.is_completed
    assert route.call_count == 2
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_wait_for_job_propagates_404_after_grace(client, monkeypatch):
    """With grace_period=0, a 404 should propagate immediately."""
    async def _no_sleep(_seconds: float) -> None:
        return None

    import asyncio as _asyncio
    monkeypatch.setattr(_asyncio, "sleep", _no_sleep)

    respx.get(f"{BASE_URL}/jobs/missing").mock(
        return_value=httpx.Response(404, json={"error": "Job not found"})
    )
    with pytest.raises(NotFoundError):
        await client.wait_for_job("missing", poll_interval=0.0, not_found_grace_period=0.0)
    await client.close()


# =============================================================================
# Network error wrapping (regression for opaque [HTTP 0] messages)
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_network_error_message_includes_method_path_and_type(client):
    """Wrapped httpx errors should include method, path and exception type for debugging."""
    from tornado_sdk.exceptions import TornadoAPIError

    respx.post(f"{BASE_URL}/metadata").mock(side_effect=httpx.ReadError("connection reset"))

    with pytest.raises(TornadoAPIError) as exc_info:
        await client.get_metadata("https://youtube.com/watch?v=abc")
    msg = str(exc_info.value)
    assert "POST" in msg
    assert "/metadata" in msg
    assert exc_info.value.status_code == 0
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_network_error_falls_back_to_class_name_when_str_empty(client):
    """If str(exc) is empty, the wrapper should still surface the exception class name."""
    from tornado_sdk.exceptions import TornadoAPIError

    # ReadError("") yields an empty str(e) — the class name is the only useful clue
    respx.post(f"{BASE_URL}/metadata").mock(side_effect=httpx.ReadError(""))
    with pytest.raises(TornadoAPIError) as exc_info:
        await client.get_metadata("https://youtube.com/watch?v=abc")
    assert "ReadError" in str(exc_info.value)
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


# =============================================================================
# bulk_youtube_jobs (fan-out around create_job)
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_bulk_youtube_jobs_returns_job_ids_in_order(client):
    """bulk_youtube_jobs should fan out POST /jobs and return job_ids in input order."""
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content)
        seen_urls.append(body["url"])
        # synthesize a job_id from the URL suffix
        return httpx.Response(201, json={"job_id": f"job-{body['url'][-1]}"})

    respx.post(f"{BASE_URL}/jobs").mock(side_effect=_handler)

    urls = [
        "https://youtube.com/watch?v=A",
        "https://youtube.com/watch?v=B",
        "https://youtube.com/watch?v=C",
    ]
    ids = await client.bulk_youtube_jobs(urls, concurrency=2, folder="test")
    assert ids == ["job-A", "job-B", "job-C"]
    # all three input URLs were submitted
    assert sorted(seen_urls) == sorted(urls)
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_bulk_youtube_jobs_return_exceptions(client):
    """With return_exceptions=True, failed creations should be returned as Exceptions."""
    from tornado_sdk import BulkJobItem

    responses = [
        httpx.Response(201, json={"job_id": "ok-1"}),
        httpx.Response(400, json={"error": "Invalid URL"}),
    ]
    respx.post(f"{BASE_URL}/jobs").mock(side_effect=responses)

    results = await client.bulk_youtube_jobs(
        [BulkJobItem(url="https://youtube.com/watch?v=X", filename="x"), "not-a-url"],
        concurrency=1,
        return_exceptions=True,
    )
    assert results[0] == "ok-1"
    assert isinstance(results[1], Exception)
    await client.close()


# =============================================================================
# Job model exposes s3_key / s3_bucket / storage_provider
# =============================================================================


@respx.mock
@pytest.mark.asyncio
async def test_get_job_exposes_s3_key_and_bucket(client):
    """Job.from_dict should populate s3_key/s3_bucket/storage_provider when present."""
    respx.get(f"{BASE_URL}/jobs/abc").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "abc",
                "url": "https://youtube.com/watch?v=abc",
                "status": "Completed",
                "s3_url": "https://r2.example.com/tornado/videos/test/file.mp4?sig=...",
                "s3_key": "videos/test/file.mp4",
                "s3_bucket": "my-bucket",
                "storage_provider": "s3",
            },
        )
    )
    job = await client.get_job("abc")
    assert job.s3_key == "videos/test/file.mp4"
    assert job.s3_bucket == "my-bucket"
    assert job.storage_provider == "s3"
    await client.close()


# =============================================================================
# Synchronous wrappers (#6) — smoke tests
# =============================================================================


@respx.mock
def test_sync_wrappers_smoke():
    """Smoke test that the new sync wrappers hit the right endpoints."""
    from tornado_sdk import S3StorageConfig

    sync_client = TornadoClient(api_key="test-key", max_retries=0)
    with sync_client as c:
        respx.post(f"{BASE_URL}/user/s3").mock(
            return_value=httpx.Response(200, json={"message": "OK", "provider": "s3"})
        )
        result = c.sync_configure_s3(
            S3StorageConfig(
                endpoint="https://s3.amazonaws.com",
                bucket="b",
                region="us-east-1",
                access_key="AK",
                secret_key="SK",
            )
        )
        assert result["provider"] == "s3"

        respx.delete(f"{BASE_URL}/user/s3").mock(
            return_value=httpx.Response(200, json={"message": "deleted"})
        )
        assert c.sync_delete_s3()["message"] == "deleted"

        respx.post(f"{BASE_URL}/batch/b1/start").mock(
            return_value=httpx.Response(200, json={"batch_id": "b1", "started_jobs": 5, "status": "processing"})
        )
        assert c.sync_start_batch("b1")["started_jobs"] == 5

        respx.patch(f"{BASE_URL}/batch/b1/jobs").mock(
            return_value=httpx.Response(200, json={"updated": 1, "errors": []})
        )
        result = c.sync_rename_batch_jobs("b1", [{"job_id": "j1", "filename": "ep1"}])
        assert result["updated"] == 1


@respx.mock
def test_sync_context_manager_closes_sync_client():
    """The synchronous context manager should close the sync client on exit."""
    respx.get(f"{BASE_URL}/usage").mock(
        return_value=httpx.Response(200, json={"client_name": "t", "usage_count": 0, "storage_usage_gb": 0.0})
    )
    with TornadoClient(api_key="k", max_retries=0) as c:
        c.sync_get_usage()
        assert c._sync_client is not None
        assert not c._sync_client.is_closed
    # After exiting the context manager, the sync client must be closed.
    assert c._sync_client.is_closed
