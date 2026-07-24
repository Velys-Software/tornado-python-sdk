"""
Tornado API client — high-performance async/sync Python SDK.

This module provides ``TornadoClient``, the main entry point for interacting
with the Tornado Video Downloader API. It supports:

- **Async methods** (default): ``create_job``, ``get_job``, ``wait_for_job``, etc.
- **Sync wrappers**: ``sync_create_job``, ``sync_get_job``, ``sync_wait_for_job``, etc.
- **Auto-retry**: Configurable retry with exponential backoff on 429 and 5xx errors.
- **Connection pooling**: Reuses HTTP connections via httpx for performance.

Usage:
    # Async (recommended for high throughput)
    async with TornadoClient(api_key="...") as client:
        job_id = await client.create_job("https://youtube.com/watch?v=...")
        job = await client.wait_for_job(job_id)

    # Sync (simpler, for scripts)
    client = TornadoClient(api_key="...")
    job_id = client.sync_create_job("https://youtube.com/watch?v=...")
    job = client.sync_wait_for_job(job_id)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import random
import time
import uuid
from typing import Any, Optional, Union, cast

import httpx

from tornado_sdk.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TornadoAPIError,
    ValidationError,
)
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
    MetadataResponse,
    OssStorageConfig,
    S3StorageConfig,
    SlackWebhookConfig,
    UsageResponse,
)


class TornadoClient:
    """Client for the Tornado Video Downloader API.

    Manages HTTP connections, authentication, retries, and response parsing.
    Supports both async and synchronous usage patterns.

    Authentication modes:
        - ``"api_key"`` (default): Sends ``x-api-key`` header. Used by direct API users.
        - ``"bearer"``: Sends ``Authorization: Bearer <token>`` header.
          Used by marketplace users (Apify, RapidAPI, Zyla).

    Args:
        api_key: Your API key or Bearer token (depending on auth_mode).
        base_url: API base URL. Default: ``https://api.tornadoapi.io``.
        timeout: HTTP request timeout in seconds. Default: 30.
        max_retries: Maximum retries on transient errors (429, 5xx).
            Uses exponential backoff (1s, 2s, 4s, ...). Default: 3.
        auth_mode: Authentication method: ``"api_key"`` or ``"bearer"``.
            Default: ``"api_key"``.
        max_backoff: Upper bound (seconds) on any single retry sleep, including a
            server-provided ``Retry-After``. Prevents an unbounded block from a
            hostile or misconfigured gateway. Default: 60.

    Example (direct API):
        >>> client = TornadoClient(api_key="sk_abc123")

    Example (Apify marketplace):
        >>> client = TornadoClient(api_key="apify_api_xxx", auth_mode="bearer")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tornadoapi.io",
        timeout: float = 30.0,
        max_retries: int = 3,
        auth_mode: str = "api_key",
        max_backoff: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        # "api_key" sends x-api-key header; "bearer" sends Authorization: Bearer
        if auth_mode not in ("api_key", "bearer"):
            raise ValueError(f"auth_mode must be 'api_key' or 'bearer', got '{auth_mode}'")
        self.auth_mode = auth_mode
        # Lazy-initialized HTTP clients (one for async, one for sync)
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None

    def _headers(self) -> dict[str, str]:
        """Build default request headers with the configured authentication method."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.auth_mode == "bearer":
            # Bearer token auth — used by Apify, RapidAPI, and Zyla marketplace users
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            # Direct API key auth — default for direct API users
            headers["x-api-key"] = self.api_key
        return headers

    @staticmethod
    def _idempotency_headers(key: Optional[str]) -> dict[str, str]:
        """Build the ``x-idempotency-key`` header for POST /jobs.

        The API deduplicates job creation on this header: if a previous
        request with the same key already created a job, it returns the
        existing ``job_id`` (with ``"cached": true``) instead of creating a
        duplicate. One key is generated per logical create call, so the
        client's internal retries (5xx / network errors) can never create
        duplicate jobs even when the original response was lost.
        """
        return {"x-idempotency-key": key or str(uuid.uuid4())}

    # =========================================================================
    # HTTP Transport Layer
    # =========================================================================

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client (lazy initialization).

        The client is reused across requests for connection pooling.
        """
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._async_client

    def _get_sync_client(self) -> httpx.Client:
        """Get or create the synchronous HTTP client (lazy initialization)."""
        if self._sync_client is None or self._sync_client.is_closed:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._sync_client

    def _retry_delay(self, retry_after: Optional[int], attempt: int) -> float:
        """Compute a single retry sleep, clamped to ``[0, max_backoff]``.

        - When the server provided a ``Retry-After``, honor it exactly (clamped
          and non-negative) — we never retry earlier than the server asked.
        - Otherwise use exponential backoff (``2 ** attempt``) with *full
          jitter* (a random value in ``[0, ceiling]``) so many clients don't
          retry in lockstep and amplify an upstream incident.

        The clamp guarantees a hostile or malformed ``Retry-After`` can never
        block the caller unboundedly, and that the delay is never negative
        (which would crash ``time.sleep`` in the sync path).
        """
        if retry_after is not None:
            return max(0.0, min(float(retry_after), self.max_backoff))
        ceiling = min(float(2 ** attempt), self.max_backoff)
        return random.uniform(0.0, ceiling)

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Execute an async HTTP request with automatic retry on transient errors.

        Retry strategy:
            - 429 (Rate Limited): Wait for Retry-After header value, or exponential backoff
            - 5xx (Server Error): Exponential backoff (2^attempt seconds)
            - Network errors (httpx.HTTPError): Exponential backoff

        Non-retryable errors (400, 401, 403, 404, 422) are raised immediately.

        ``headers`` are per-request extras merged over the client defaults
        (e.g. ``x-idempotency-key``); they are identical across retries so a
        retried POST is deduplicated server-side.
        """
        client = await self._get_async_client()
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(
                    method, path, json=json, params=params, headers=headers
                )
                return self._handle_response(response)
            except (RateLimitError, TornadoAPIError) as e:
                # Retry on rate limit (429) — but ONLY while retries remain, and
                # with the sleep clamped. This makes max_retries=0 fail fast and
                # prevents a server-controlled Retry-After from blocking forever.
                if isinstance(e, RateLimitError):
                    if attempt < self.max_retries:
                        await asyncio.sleep(self._retry_delay(e.retry_after, attempt))
                        last_exc = e
                        continue
                    raise
                # Retry on server errors (5xx) with clamped backoff
                if isinstance(e, TornadoAPIError) and e.status_code >= 500:
                    if attempt < self.max_retries:
                        await asyncio.sleep(self._retry_delay(None, attempt))
                        last_exc = e
                        continue
                # Non-retryable API errors (400, 401, 403, 404) — raise immediately
                raise
            except httpx.HTTPError as e:
                # Network-level errors (timeout, connection refused, etc.)
                if attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay(None, attempt))
                    last_exc = e
                    continue
                raise TornadoAPIError(
                    self._format_network_error(method, path, e), 0
                ) from e

        # All retries exhausted — raise the last error
        raise last_exc  # type: ignore[misc]

    def _request_sync(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Execute a synchronous HTTP request with automatic retry.

        Same retry logic as ``_request()`` but uses time.sleep instead of asyncio.sleep.
        """
        client = self._get_sync_client()
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = client.request(
                    method, path, json=json, params=params, headers=headers
                )
                return self._handle_response(response)
            except (RateLimitError, TornadoAPIError) as e:
                if isinstance(e, RateLimitError):
                    if attempt < self.max_retries:
                        time.sleep(self._retry_delay(e.retry_after, attempt))
                        last_exc = e
                        continue
                    raise
                if isinstance(e, TornadoAPIError) and e.status_code >= 500:
                    if attempt < self.max_retries:
                        time.sleep(self._retry_delay(None, attempt))
                        last_exc = e
                        continue
                raise
            except httpx.HTTPError as e:
                if attempt < self.max_retries:
                    time.sleep(self._retry_delay(None, attempt))
                    last_exc = e
                    continue
                raise TornadoAPIError(
                    self._format_network_error(method, path, e), 0
                ) from e

        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _format_network_error(method: str, path: str, exc: Exception) -> str:
        """Format a network-level exception into a debuggable message.

        ``str(exc)`` is often empty for low-level httpx errors (ReadError,
        RemoteProtocolError) — fall back to the exception class name so the
        caller still has a useful clue.
        """
        detail = str(exc) or type(exc).__name__
        return f"Network error on {method} {path}: {detail}"

    @staticmethod
    def _handle_response(response: httpx.Response) -> dict[str, Any]:
        """Parse API response and raise typed exceptions for error status codes.

        Success (200, 201, 204): Returns parsed JSON body, or {} if the body is
        empty / null / not a JSON object.
        Errors: Raises the appropriate TornadoAPIError subclass.
        """
        def _safe_json() -> Any:
            # Empty body (e.g. 204 No Content) — json() would raise
            if not response.content:
                return None
            try:
                return response.json()
            except Exception:
                return None

        # Success responses — coerce non-dict bodies (None, list, scalar) to {}
        # so callers can rely on the dict[str, Any] return contract.
        if response.status_code in (200, 201, 204):
            body = _safe_json()
            return body if isinstance(body, dict) else {}

        # Error path — body may be None, a non-dict, or a plain text error.
        # Some endpoints (GET /jobs/:id, GET /batch/:id) return a literal JSON
        # `null` body on 401/404 — treat that like an empty body, not "null".
        body = _safe_json()
        if not isinstance(body, dict):
            text = (response.text or "").strip()
            if text == "null":
                text = ""
            body = {"error": text or f"HTTP {response.status_code}"}

        error_msg = body.get("error") or f"HTTP {response.status_code}"

        # Map HTTP status codes to specific exception types
        if response.status_code in (401, 403):
            raise AuthenticationError(error_msg, response.status_code, body)
        elif response.status_code == 404:
            raise NotFoundError(error_msg, response.status_code, body)
        elif response.status_code == 429:
            # Extract Retry-After header for rate limit backoff
            retry_after = None
            if "Retry-After" in response.headers:
                try:
                    # Clamp to >= 0: a negative Retry-After would otherwise crash
                    # time.sleep() in the sync retry path with a raw ValueError.
                    retry_after = max(0, int(response.headers["Retry-After"]))
                except ValueError:
                    # Non-integer (e.g. RFC 7231 HTTP-date) — fall back to backoff.
                    pass
            raise RateLimitError(error_msg, 429, body, retry_after)
        elif response.status_code in (400, 422):
            # 400: application-level validation errors ({"error": ...}).
            # 422: axum's JSON deserialization rejections (wrong type, out-of-
            # range value like video_quality > 255) — same "fix your request"
            # semantics, so surface both as ValidationError.
            raise ValidationError(error_msg, response.status_code, body)
        else:
            raise TornadoAPIError(error_msg, response.status_code, body)

    # =========================================================================
    # Connection Lifecycle
    # =========================================================================

    async def close(self) -> None:
        """Close the underlying HTTP clients and release connections.

        Should be called when you're done using the client, or use
        the async context manager instead (``async with TornadoClient(...) as client:``).
        """
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()

    def sync_close(self) -> None:
        """Close the synchronous HTTP client only.

        Use this from synchronous code where ``close()`` (async) cannot be
        awaited. The async client, if it was lazily created, must still be
        closed via ``await close()`` from an event loop.
        """
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()

    async def __aenter__(self) -> TornadoClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager — closes HTTP clients."""
        await self.close()

    def __enter__(self) -> TornadoClient:
        """Enter synchronous context manager (``with TornadoClient(...) as client:``)."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit synchronous context manager — closes the sync HTTP client."""
        self.sync_close()

    # =========================================================================
    # Jobs — Single Video Downloads
    # =========================================================================

    async def create_job(
        self,
        url: str,
        *,
        webhook_url: Optional[str] = None,
        format: Optional[str] = None,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        video_quality: Optional[int] = None,
        filename: Optional[str] = None,
        folder: Optional[str] = None,
        audio_only: bool = False,
        download_subtitles: bool = False,
        download_thumbnail: bool = False,
        quality_preset: Optional[str] = None,
        max_resolution: Optional[str] = None,
        clip_start: Optional[str] = None,
        clip_end: Optional[str] = None,
        live_recording: bool = False,
        live_from_start: bool = False,
        max_duration: Optional[int] = None,
        wait_for_video: bool = False,
        enable_progress_webhook: bool = False,
        storage: Optional[InlineStorageConfig] = None,
        paused: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Create a new download job.

        Submits a video URL to the Tornado API for download, processing,
        and upload to your configured cloud storage.

        Batch URLs: for Spotify show URLs (``/show/``) AND YouTube playlist
        URLs (``?list=...``), the API extracts all episodes/videos and
        returns a ``batch_id`` instead of a ``job_id``. Use
        ``create_job_full()`` if you need the full batch payload (episode
        lists use different keys: ``episode_jobs`` for Spotify shows,
        ``video_jobs`` for YouTube playlists).

        Idempotency: an ``x-idempotency-key`` header is sent automatically
        (a random UUID per call, stable across internal retries), so a
        retried POST after a lost response cannot create a duplicate job.
        Pass ``idempotency_key`` explicitly to deduplicate across your own
        application-level retries.

        Args:
            url: Video URL to download.
            idempotency_key: Optional explicit idempotency key. Auto-generated
                when omitted.
            **kwargs: See CreateJobRequest for all available parameters.

        Returns:
            Job ID (str) for single videos, or batch ID for Spotify shows
            and YouTube playlists.
        """
        req = CreateJobRequest(
            url=url,
            webhook_url=webhook_url,
            format=format,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            video_quality=video_quality,
            filename=filename,
            folder=folder,
            audio_only=audio_only,
            download_subtitles=download_subtitles,
            download_thumbnail=download_thumbnail,
            quality_preset=quality_preset,
            max_resolution=max_resolution,
            clip_start=clip_start,
            clip_end=clip_end,
            live_recording=live_recording,
            live_from_start=live_from_start,
            max_duration=max_duration,
            wait_for_video=wait_for_video,
            enable_progress_webhook=enable_progress_webhook,
            storage=storage,
            paused=paused,
        )
        data = await self._request(
            "POST", "/jobs", json=req.to_dict(),
            headers=self._idempotency_headers(idempotency_key),
        )
        # API returns {"job_id": "..."} for single jobs,
        # {"batch_id": "...", "total_episodes": N, ...} for Spotify shows,
        # or {"batch_id": "...", "total_videos": N, ...} for YouTube playlists
        return data.get("job_id") or data.get("batch_id", "")

    async def create_job_full(
        self,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a download job and return the full raw API response.

        Unlike ``create_job()`` which returns just the ID, this returns the
        complete response dict. Useful for batch URLs where you need the
        item list and batch metadata. Response shapes:

        - Single video: ``{"job_id": "..."}`` (plus ``"cached": true`` when
          an idempotency key matched a previous request)
        - Spotify show: ``{"batch_id", "total_episodes", "paused",
          "episodes": [{job_id, url, title}, ...], "episode_jobs": [...]}``
        - YouTube playlist: ``{"batch_id", "total_videos", "video_jobs": [...]}``

        Accepts the same ``idempotency_key`` keyword as ``create_job()``.

        Returns:
            Raw API response dict (job_id or batch_id + metadata).
        """
        idempotency_key = kwargs.pop("idempotency_key", None)
        req = CreateJobRequest(url=url, **kwargs)
        return await self._request(
            "POST", "/jobs", json=req.to_dict(),
            headers=self._idempotency_headers(idempotency_key),
        )

    async def get_job(self, job_id: str) -> Job:
        """Get the current status and details of a download job.

        Args:
            job_id: The UUID returned by create_job().

        Returns:
            Job object with status, output URL, metrics, etc. Fresh jobs
            (served from the API's cache) only carry the core fields; full
            telemetry and the parameter echo appear once the job is
            persisted (typically within seconds of completion).

        Raises:
            NotFoundError: If the job ID is unknown or belongs to another
                API key. (Jobs persist beyond the 24h cache window — only
                the *active-job* cache expires, completed jobs remain
                queryable from the database.)
            ValidationError: If job_id is not a valid UUID.
        """
        data = await self._request("GET", f"/jobs/{job_id}")
        return Job.from_dict(data)

    async def list_jobs(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        status: Optional[str] = None,
    ) -> tuple[list[Job], int]:
        """List your jobs with optional pagination and status filtering.

        .. note::
            List items include the raw ``s3_key`` but NOT the presigned
            ``s3_url``/``subtitle_url``/``thumbnail_url`` — call
            ``get_job(id)`` to obtain a download URL for a specific job.

        Args:
            limit: Maximum number of jobs to return. Server default: 20,
                server-side maximum: 100 (higher values are clamped).
            offset: Number of jobs to skip (for pagination).
            status: Filter by status (case-insensitive; normalized to lowercase
                for the API). Valid values: "pending", "processing",
                "completed", "failed", "warning". Any other value (including
                "skipped" and "cancelled") is silently IGNORED by the API,
                which then returns the unfiltered list.

        Returns:
            Tuple of (list of Job objects, total count). ``total`` is the
            total number of jobs for this API key — it does NOT reflect the
            ``status`` filter.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if status is not None:
            # The API expects lowercase status filters (pending, completed, ...);
            # callers naturally pass the PascalCase Job.status value, so normalize.
            params["status"] = status.lower()

        data = await self._request("GET", "/jobs", params=params)
        jobs = [Job.from_dict(j) for j in data.get("jobs", [])]
        return jobs, data.get("total", len(jobs))

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a job that is still queued (not yet picked up by a worker).

        Only jobs still waiting in the queue can be cancelled. Jobs already
        processing, completed or failed cannot — the API returns 400
        ("not in queue or already processing") in that case.

        .. warning::
            Do NOT call ``wait_for_job()`` on a job you just cancelled.
            The API has no "Cancelled" status: the job is persisted as
            ``Failed`` (with ``step == "Cancelled"``), but its cache entry
            may keep reporting ``Pending`` for up to ~24h, which would make
            a wait loop spin until its timeout. Use ``Job.is_cancelled``
            to recognize a cancelled job when you encounter one later.

        Args:
            job_id: The UUID of the job to cancel.

        Returns:
            Dict ``{"message": "...", "job_id": "..."}`` on success.

        Raises:
            ValidationError: If the job is already processing or terminal.
        """
        return await self._request("DELETE", f"/jobs/{job_id}")

    async def retry_job(self, job_id: str) -> dict[str, Any]:
        """Retry a failed or warning job with the same parameters.

        Creates a brand-new job reusing all original parameters. Only jobs
        with status ``Failed`` or ``Warning`` can be retried (400 otherwise).

        Args:
            job_id: The UUID of the failed/warning job to retry.

        Returns:
            Dict ``{"job_id": <new id>, "original_job_id": ..., "message": ...}``.

        Raises:
            ValidationError: If the job is not in Failed/Warning status.
        """
        return await self._request("POST", f"/jobs/{job_id}/retry")

    async def delete_job_file(self, job_id: str) -> dict[str, Any]:
        """Delete the output file of a completed job from cloud storage.

        Frees up storage space. The job record remains but s3_url becomes invalid.

        Args:
            job_id: The UUID of the completed job whose file to delete.

        Returns:
            API response dict confirming deletion.
        """
        return await self._request("DELETE", f"/jobs/{job_id}/file")

    async def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
        not_found_grace_period: float = 30.0,
    ) -> Job:
        """Poll a job until it reaches a terminal state (Completed/Failed/Cancelled).

        This is a convenience method that repeatedly calls get_job() until
        the job finishes. Use this instead of writing your own polling loop.

        Args:
            job_id: The UUID of the job to wait for.
            poll_interval: Seconds between status checks. Default: 2.0.
            timeout: Maximum seconds to wait. None means wait indefinitely.
            not_found_grace_period: Seconds to keep polling on NotFoundError
                before propagating it. Tolerates a create-then-read replication
                lag where get_job() briefly 404s right after create_job().
                Set to 0.0 to disable. Default: 30.0.

        Returns:
            The final Job object in its terminal state.

        Raises:
            TimeoutError: If the timeout is reached before the job completes.
            NotFoundError: If the job is still missing after the grace period.
        """
        start = time.monotonic()
        while True:
            try:
                job = await self.get_job(job_id)
            except NotFoundError:
                if (time.monotonic() - start) < not_found_grace_period:
                    await asyncio.sleep(poll_interval)
                    continue
                raise
            if job.is_terminal:
                return job
            if timeout is not None and (time.monotonic() - start) >= timeout:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout}s (status: {job.status.value})"
                )
            await asyncio.sleep(poll_interval)

    # =========================================================================
    # Bulk Jobs — Multiple Videos at Once
    # =========================================================================

    async def create_bulk_jobs(
        self,
        jobs: list[Union[str, BulkJobItem, dict[str, Any]]],
        *,
        folder: Optional[str] = None,
        format: Optional[str] = None,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
        audio_bitrate: Optional[str] = None,
        video_quality: Optional[int] = None,
        audio_only: bool = False,
        download_subtitles: bool = False,
        download_thumbnail: bool = False,
        quality_preset: Optional[str] = None,
        max_resolution: Optional[str] = None,
        clip_start: Optional[str] = None,
        clip_end: Optional[str] = None,
        live_recording: bool = False,
        live_from_start: bool = False,
        max_duration: Optional[int] = None,
        wait_for_video: bool = False,
    ) -> dict[str, Any]:
        """Create multiple download jobs at once (max 100 per request).

        All jobs share the same encoding options but can have individual filenames.
        Accepts a flexible list of URLs, BulkJobItem objects, or dicts.

        The returned ``job_ids`` are regular jobs: each is addressable via
        ``get_job()`` / ``wait_for_job()`` (allow for a short creation lag —
        the default ``not_found_grace_period`` covers it).

        Endpoint limitations (per the API):

        - The returned ``batch_id`` is a grouping label only — there is NO
          batch record behind it, so ``get_batch()`` / ``wait_for_batch()`` /
          ``start_batch()`` / ``rename_batch_jobs()`` return 404 for it.
          Those endpoints only work for Spotify-show batches created via
          ``create_job()``. Track progress per job via the ``job_ids``.
        - ``webhook_url`` and ``enable_progress_webhook`` are NOT supported
          in bulk (silently disabled server-side), and ``paused`` mode is
          unavailable.
        - Marketplace users (``auth_mode="bearer"``) get 403 — bulk is
          direct-API only.

        If you need per-job webhooks, inline storage, or paused mode, use
        :meth:`bulk_youtube_jobs` instead: it fans out individual
        ``create_job()`` calls under a concurrency limit and supports every
        ``create_job`` option.

        Args:
            jobs: List of video URLs. Each item can be:
                - A plain URL string
                - A BulkJobItem(url=..., filename=...)
                - A dict with "url" and optional "filename" keys
            **kwargs: Shared encoding options (see CreateBulkRequest).

        Returns:
            Dict with ``batch_id``, ``total_jobs``, and ``job_ids`` list.

        Raises:
            ValidationError: If more than 100 jobs are provided.
            ValueError: If a job item is not a str, BulkJobItem, or dict.
        """
        # Normalize heterogeneous input into BulkJobItem list
        items: list[BulkJobItem] = []
        for j in jobs:
            if isinstance(j, str):
                items.append(BulkJobItem(url=j))
            elif isinstance(j, BulkJobItem):
                items.append(j)
            elif isinstance(j, dict):
                items.append(BulkJobItem(url=j["url"], filename=j.get("filename")))
            else:
                raise ValueError(f"Invalid job item type: {type(j)}")

        if len(items) > 100:
            raise ValidationError(
                f"Bulk request supports at most 100 jobs, got {len(items)}.", 400
            )

        req = CreateBulkRequest(
            jobs=items,
            folder=folder,
            format=format,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            video_quality=video_quality,
            audio_only=audio_only,
            download_subtitles=download_subtitles,
            download_thumbnail=download_thumbnail,
            quality_preset=quality_preset,
            max_resolution=max_resolution,
            clip_start=clip_start,
            clip_end=clip_end,
            live_recording=live_recording,
            live_from_start=live_from_start,
            max_duration=max_duration,
            wait_for_video=wait_for_video,
        )
        return await self._request("POST", "/jobs/bulk", json=req.to_dict())

    async def bulk_youtube_jobs(
        self,
        urls: list[Union[str, BulkJobItem, dict[str, Any]]],
        *,
        concurrency: int = 8,
        return_exceptions: bool = False,
        **job_kwargs: Any,
    ) -> list[Union[str, Exception]]:
        """Fan out ``create_job()`` calls for a list of YouTube URLs.

        Alternative to :meth:`create_bulk_jobs` that supports every
        ``create_job`` option: per-job ``webhook_url``, progress webhooks,
        inline ``storage`` credentials, ``paused`` mode… none of which the
        ``/jobs/bulk`` endpoint accepts. It invokes ``POST /jobs`` once per
        URL — under an ``asyncio.Semaphore`` to bound concurrency — and each
        call carries its own idempotency key, so retries never duplicate jobs.

        .. note::
            Careful with playlist URLs here: a URL containing ``?list=``
            makes the API create a *batch* and the returned ID is a
            ``batch_id``, not a ``job_id``.

        Args:
            urls: List of URLs. Each item can be a string, a ``BulkJobItem``
                (to override ``filename``), or a dict with ``url`` / ``filename``.
            concurrency: Maximum concurrent ``create_job`` calls. Default: 8.
            return_exceptions: If True, failed creations are returned as
                Exception objects in the result list (same index as the input).
                If False (default), the first failure is raised.
            **job_kwargs: Forwarded as keyword arguments to ``create_job``
                (e.g. ``folder``, ``audio_only``, ``download_thumbnail``,
                ``storage``, …). Per-item ``filename`` from BulkJobItem/dict
                overrides any ``filename`` passed in ``job_kwargs``.

        Returns:
            List of job_ids (str) in the same order as the input. When
            ``return_exceptions=True``, failed items are Exception objects.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _one(item: Union[str, BulkJobItem, dict[str, Any]]) -> str:
            if isinstance(item, str):
                url, per_item_filename = item, None
            elif isinstance(item, BulkJobItem):
                url, per_item_filename = item.url, item.filename
            elif isinstance(item, dict):
                url, per_item_filename = item["url"], item.get("filename")
            else:
                raise ValueError(f"Invalid job item type: {type(item)}")

            kwargs = dict(job_kwargs)
            if per_item_filename is not None:
                kwargs["filename"] = per_item_filename
            async with semaphore:
                return await self.create_job(url, **kwargs)

        results = await asyncio.gather(
            *(_one(u) for u in urls), return_exceptions=return_exceptions
        )
        # gather(return_exceptions=True) is typed as BaseException, but a failed
        # create_job yields a TornadoError (an Exception). Preserve the
        # documented list[str | Exception] contract.
        return cast("list[Union[str, Exception]]", list(results))

    # =========================================================================
    # Batch Operations — Spotify Shows
    # =========================================================================

    async def get_batch(self, batch_id: str) -> BatchJob:
        """Get the status and progress of a batch (Spotify show) download.

        Args:
            batch_id: The batch UUID returned by create_job() for Spotify show URLs.

        Returns:
            BatchJob with episode counts and progress info.
        """
        data = await self._request("GET", f"/batch/{batch_id}")
        return BatchJob.from_dict(data)

    async def rename_batch_jobs(
        self, batch_id: str, renames: list[dict[str, str]]
    ) -> dict[str, Any]:
        """Rename episode filenames in a paused batch before starting downloads.

        The batch must be in "paused" status (created with paused=True).

        Args:
            batch_id: The batch UUID.
            renames: List of rename operations, each a dict with:
                - "job_id": UUID of the episode job
                - "filename": New filename (without extension)

        Returns:
            Dict with ``updated`` count and ``errors`` list.
        """
        return await self._request(
            "PATCH", f"/batch/{batch_id}/jobs", json={"renames": renames}
        )

    async def start_batch(self, batch_id: str) -> dict[str, Any]:
        """Start a paused batch, enqueueing all episode jobs for processing.

        The batch must be in "paused" status. After starting, jobs are
        processed according to available worker capacity.

        Args:
            batch_id: The batch UUID.

        Returns:
            Dict with ``batch_id``, ``started_jobs`` count, and ``status``.
        """
        return await self._request("POST", f"/batch/{batch_id}/start")

    async def wait_for_batch(
        self,
        batch_id: str,
        *,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
        not_found_grace_period: float = 30.0,
    ) -> BatchJob:
        """Poll a batch until all episodes are done (completed or failed).

        Args:
            batch_id: The batch UUID.
            poll_interval: Seconds between status checks. Default: 5.0.
            timeout: Maximum seconds to wait. None means wait indefinitely.
            not_found_grace_period: Seconds to keep polling on NotFoundError
                before propagating it. Tolerates a create-then-read replication
                lag right after the batch was created. Set to 0.0 to disable.
                Default: 30.0.

        Returns:
            The final BatchJob object with episode completion counts.

        Raises:
            TimeoutError: If timeout is reached before the batch finishes.
            NotFoundError: If the batch is still missing after the grace period.
        """
        start = time.monotonic()
        while True:
            try:
                batch = await self.get_batch(batch_id)
            except NotFoundError:
                if (time.monotonic() - start) < not_found_grace_period:
                    await asyncio.sleep(poll_interval)
                    continue
                raise
            # Terminal batch status (completed = all succeeded, finished = done
            # with failures and/or skips). The episode-count check below is a
            # fallback for a batch still reporting "processing" once all
            # episodes finish — it must count skipped episodes too, or a batch
            # with skips would never satisfy it.
            if batch.is_terminal:
                return batch
            if batch.done_episodes >= batch.total_episodes and batch.total_episodes > 0:
                return batch
            if timeout is not None and (time.monotonic() - start) >= timeout:
                raise TimeoutError(
                    f"Batch {batch_id} did not complete within {timeout}s"
                )
            await asyncio.sleep(poll_interval)

    # =========================================================================
    # Metadata — Video Info Without Downloading
    # =========================================================================

    async def get_metadata(self, url: str) -> MetadataResponse:
        """Extract video metadata without downloading the video.

        Useful for preview UIs, URL validation, or checking video properties
        before submitting a download job.

        Args:
            url: Video URL to extract metadata from.

        Returns:
            MetadataResponse with title, duration, resolution, thumbnail, etc.
        """
        data = await self._request("POST", "/metadata", json={"url": url})
        return MetadataResponse.from_dict(data)

    async def is_short(self, url: str) -> IsShortResponse:
        """Detect whether a YouTube URL is a Short (vertical video).

        Classification is done by aspect ratio of the best available format
        (height > width => short). No download is performed.

        Args:
            url: YouTube video/short URL.

        Returns:
            IsShortResponse with is_short, video_type ("short"/"video"/"live"),
            dimensions and duration.
        """
        data = await self._request("POST", "/is-short", json={"url": url})
        return IsShortResponse.from_dict(data)

    # =========================================================================
    # Usage — Account Statistics
    # =========================================================================

    async def get_usage(self) -> UsageResponse:
        """Get your API usage statistics and storage consumption.

        Returns:
            UsageResponse with job count, storage usage, billing info, and limits.
        """
        data = await self._request("GET", "/usage")
        return UsageResponse.from_dict(data)

    # =========================================================================
    # Storage Configuration — Multi-Cloud Setup
    # =========================================================================
    # NOTE: all /user/* endpoints are DIRECT API only. Marketplace users
    # (auth_mode="bearer" via Apify/RapidAPI/Zyla) cannot call them — use
    # inline per-job storage (InlineStorageConfig) instead.

    async def configure_s3(self, config: S3StorageConfig) -> dict[str, Any]:
        """Configure S3-compatible storage for your account.

        Works with AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces, etc.
        Credentials are validated before saving.

        Args:
            config: S3 storage configuration with endpoint, bucket, and credentials.

        Returns:
            Confirmation dict with provider and bucket info.
        """
        return await self._request("POST", "/user/s3", json=config.to_dict())

    async def delete_s3(self) -> dict[str, Any]:
        """Remove your S3 storage configuration. Falls back to server default storage."""
        return await self._request("DELETE", "/user/s3")

    async def get_s3(self) -> dict[str, Any]:
        """Inspect the S3 storage configuration saved for this API key.

        Secrets are never returned: at most ``access_key_masked`` shows the
        last 4 characters of the access key (legacy storage mode only).

        Returns:
            Dict with ``configured`` (bool) and, when configured:
            ``provider``, ``container_or_bucket``, ``endpoint``, ``region``,
            ``folder_prefix``, ``base_folder``, ``access_key_masked``,
            ``last_modified``, ``source`` ("keyvault" or "legacy").
        """
        return await self._request("GET", "/user/s3")

    async def configure_blob(self, config: BlobStorageConfig) -> dict[str, Any]:
        """Configure Azure Blob Storage for your account.

        Args:
            config: Azure Blob config with account name, container, and credentials.

        Returns:
            Confirmation dict with provider and container info.
        """
        return await self._request("POST", "/user/blob", json=config.to_dict())

    async def delete_blob(self) -> dict[str, Any]:
        """Remove your Azure Blob storage configuration."""
        return await self._request("DELETE", "/user/blob")

    async def configure_gcs(self, config: GcsStorageConfig) -> dict[str, Any]:
        """Configure Google Cloud Storage for your account.

        Args:
            config: GCS config with project ID, bucket, and service account JSON.

        Returns:
            Confirmation dict with provider and bucket info.
        """
        return await self._request("POST", "/user/gcs", json=config.to_dict())

    async def delete_gcs(self) -> dict[str, Any]:
        """Remove your Google Cloud Storage configuration."""
        return await self._request("DELETE", "/user/gcs")

    async def configure_gdrive(self, config: GDriveStorageConfig) -> dict[str, Any]:
        """Configure Google Drive delivery for your account.

        Files are uploaded to the given Drive folder using a service account.
        Remember to share the target folder with the service account's email.

        Args:
            config: Google Drive config with folder_id and service account JSON.

        Returns:
            Confirmation dict with provider and folder info.
        """
        return await self._request("POST", "/user/gdrive", json=config.to_dict())

    async def delete_gdrive(self) -> dict[str, Any]:
        """Remove your Google Drive delivery configuration."""
        return await self._request("DELETE", "/user/gdrive")

    async def configure_oss(self, config: OssStorageConfig) -> dict[str, Any]:
        """Configure Alibaba Cloud OSS for your account.

        Args:
            config: OSS config with endpoint, bucket, and credentials.

        Returns:
            Confirmation dict with provider and bucket info.
        """
        return await self._request("POST", "/user/oss", json=config.to_dict())

    async def delete_oss(self) -> dict[str, Any]:
        """Remove your Alibaba Cloud OSS configuration."""
        return await self._request("DELETE", "/user/oss")

    async def configure_bucket(
        self,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> dict[str, Any]:
        """Configure legacy S3 bucket (shorthand for configure_s3).

        This is the original bucket configuration endpoint. For new integrations,
        prefer ``configure_s3()`` which supports folder_prefix and base_folder.
        """
        return await self._request(
            "POST",
            "/user/bucket",
            json={
                "endpoint": endpoint,
                "bucket": bucket,
                "region": region,
                "access_key": access_key,
                "secret_key": secret_key,
            },
        )

    async def delete_bucket(self) -> dict[str, Any]:
        """Remove legacy bucket configuration."""
        return await self._request("DELETE", "/user/bucket")

    # =========================================================================
    # Slack Notifications
    # =========================================================================

    async def configure_slack(self, config: SlackWebhookConfig) -> dict[str, Any]:
        """Configure Slack webhook notifications for job failure events.

        Sends alerts to your Slack channel when jobs fail or encounter
        warnings (private videos, bot detection, etc.).

        Args:
            config: Slack webhook config with URL and notification level.

        Returns:
            Confirmation dict.
        """
        return await self._request("POST", "/user/slack", json=config.to_dict())

    async def delete_slack(self) -> dict[str, Any]:
        """Remove Slack webhook notification configuration."""
        return await self._request("DELETE", "/user/slack")

    # =========================================================================
    # Webhook Signing — Secret Management & Signature Verification
    # =========================================================================

    async def get_webhook_secret(self) -> str:
        """Get (or lazily create) this API key's webhook signing secret.

        Every outcome webhook (job_completed / job_failed / job_warning /
        job_skipped / batch_completed) is sent with an ``X-Tornado-Signature``
        header signed with this secret. Verify incoming webhooks with
        :meth:`verify_webhook_signature`.

        Returns:
            The signing secret string (``"whsec_..."``). Generated on first
            call if the key doesn't have one yet.
        """
        data = await self._request("GET", "/user/webhook-secret")
        return data.get("webhook_signing_secret", "")

    async def rotate_webhook_secret(self) -> str:
        """Rotate (regenerate) this API key's webhook signing secret.

        The previous secret stops matching future webhook signatures
        immediately — update your webhook receiver before/right after calling.

        Returns:
            The NEW signing secret string (``"whsec_..."``).
        """
        data = await self._request("POST", "/user/webhook-secret/rotate")
        return data.get("webhook_signing_secret", "")

    @staticmethod
    def verify_webhook_signature(
        payload: Union[str, bytes],
        signature_header: str,
        secret: str,
        tolerance_seconds: int = 300,
    ) -> bool:
        """Verify an ``X-Tornado-Signature`` webhook header.

        The API signs every outcome webhook with
        ``t=<unix_ts>,v1=<hex_hmac_sha256>`` where the HMAC is computed over
        ``"{timestamp}.{raw_body}"`` using your webhook signing secret (see
        :meth:`get_webhook_secret`). This helper recomputes the HMAC over the
        exact raw body you received, compares in constant time, and rejects
        stale timestamps to guard against replay.

        Args:
            payload: The EXACT raw request body as received (bytes preferred;
                do not re-serialize parsed JSON — key order matters).
            signature_header: Value of the ``X-Tornado-Signature`` header.
            secret: Your webhook signing secret (``"whsec_..."``).
            tolerance_seconds: Maximum allowed age (absolute clock skew) of
                the signature timestamp. Default: 300 (5 minutes).
                Pass 0 to skip the timestamp check (not recommended).

        Returns:
            True if the signature is valid and fresh, False otherwise.
            Never raises on malformed input.
        """
        try:
            parts = dict(
                item.split("=", 1) for item in signature_header.split(",") if "=" in item
            )
            timestamp = parts["t"]
            expected_sig = parts["v1"]
        except (KeyError, ValueError):
            return False

        if tolerance_seconds:
            try:
                ts = int(timestamp)
            except ValueError:
                return False
            if abs(time.time() - ts) > tolerance_seconds:
                return False

        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        signed_payload = timestamp.encode("ascii") + b"." + body
        computed = hmac.new(
            secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, expected_sig)

    # =========================================================================
    # Synchronous Wrappers
    # =========================================================================
    # These methods mirror the async API but use synchronous HTTP calls.
    # Ideal for scripts, CLI tools, and environments without an event loop.

    def sync_create_job(self, url: str, **kwargs: Any) -> str:
        """Synchronous version of ``create_job()``. Returns job_id or batch_id.

        Accepts the same ``idempotency_key`` keyword (auto-generated when omitted).
        """
        idempotency_key = kwargs.pop("idempotency_key", None)
        req = CreateJobRequest(url=url, **kwargs)
        data = self._request_sync(
            "POST", "/jobs", json=req.to_dict(),
            headers=self._idempotency_headers(idempotency_key),
        )
        return data.get("job_id") or data.get("batch_id", "")

    def sync_get_job(self, job_id: str) -> Job:
        """Synchronous version of ``get_job()``. Returns Job object."""
        data = self._request_sync("GET", f"/jobs/{job_id}")
        return Job.from_dict(data)

    def sync_list_jobs(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        status: Optional[str] = None,
    ) -> tuple[list[Job], int]:
        """Synchronous version of ``list_jobs()``. Returns (jobs, total).

        ``status`` is case-insensitive and normalized to lowercase for the API.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if status is not None:
            params["status"] = status.lower()
        data = self._request_sync("GET", "/jobs", params=params)
        jobs = [Job.from_dict(j) for j in data.get("jobs", [])]
        return jobs, data.get("total", len(jobs))

    def sync_cancel_job(self, job_id: str) -> dict[str, Any]:
        """Synchronous version of ``cancel_job()``."""
        return self._request_sync("DELETE", f"/jobs/{job_id}")

    def sync_retry_job(self, job_id: str) -> dict[str, Any]:
        """Synchronous version of ``retry_job()``."""
        return self._request_sync("POST", f"/jobs/{job_id}/retry")

    def sync_delete_job_file(self, job_id: str) -> dict[str, Any]:
        """Synchronous version of ``delete_job_file()``."""
        return self._request_sync("DELETE", f"/jobs/{job_id}/file")

    def sync_get_metadata(self, url: str) -> MetadataResponse:
        """Synchronous version of ``get_metadata()``. Returns MetadataResponse."""
        data = self._request_sync("POST", "/metadata", json={"url": url})
        return MetadataResponse.from_dict(data)

    def sync_is_short(self, url: str) -> IsShortResponse:
        """Synchronous version of ``is_short()``. Returns IsShortResponse."""
        data = self._request_sync("POST", "/is-short", json={"url": url})
        return IsShortResponse.from_dict(data)

    def sync_get_usage(self) -> UsageResponse:
        """Synchronous version of ``get_usage()``. Returns UsageResponse."""
        data = self._request_sync("GET", "/usage")
        return UsageResponse.from_dict(data)

    def sync_get_batch(self, batch_id: str) -> BatchJob:
        """Synchronous version of ``get_batch()``. Returns BatchJob."""
        data = self._request_sync("GET", f"/batch/{batch_id}")
        return BatchJob.from_dict(data)

    def sync_create_bulk_jobs(
        self,
        jobs: list[Union[str, BulkJobItem, dict[str, Any]]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Synchronous version of ``create_bulk_jobs()``.

        Returns dict with batch_id, total_jobs, job_ids.
        """
        # Normalize input to BulkJobItem list
        items: list[BulkJobItem] = []
        for j in jobs:
            if isinstance(j, str):
                items.append(BulkJobItem(url=j))
            elif isinstance(j, BulkJobItem):
                items.append(j)
            elif isinstance(j, dict):
                items.append(BulkJobItem(url=j["url"], filename=j.get("filename")))
            else:
                raise ValueError(f"Invalid job item type: {type(j)}")
        if len(items) > 100:
            raise ValidationError(
                f"Bulk request supports at most 100 jobs, got {len(items)}.", 400
            )
        req = CreateBulkRequest(jobs=items, **kwargs)
        return self._request_sync("POST", "/jobs/bulk", json=req.to_dict())

    def sync_wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
        not_found_grace_period: float = 30.0,
    ) -> Job:
        """Synchronous version of ``wait_for_job()``.

        Blocks the current thread until the job reaches a terminal state.
        See ``wait_for_job()`` for ``not_found_grace_period`` semantics.
        """
        start_t = time.monotonic()
        while True:
            try:
                job = self.sync_get_job(job_id)
            except NotFoundError:
                if (time.monotonic() - start_t) < not_found_grace_period:
                    time.sleep(poll_interval)
                    continue
                raise
            if job.is_terminal:
                return job
            if timeout is not None and (time.monotonic() - start_t) >= timeout:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout}s (status: {job.status.value})"
                )
            time.sleep(poll_interval)

    def sync_create_job_full(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Synchronous version of ``create_job_full()``. Returns the raw API response."""
        idempotency_key = kwargs.pop("idempotency_key", None)
        req = CreateJobRequest(url=url, **kwargs)
        return self._request_sync(
            "POST", "/jobs", json=req.to_dict(),
            headers=self._idempotency_headers(idempotency_key),
        )

    def sync_start_batch(self, batch_id: str) -> dict[str, Any]:
        """Synchronous version of ``start_batch()``."""
        return self._request_sync("POST", f"/batch/{batch_id}/start")

    def sync_rename_batch_jobs(
        self, batch_id: str, renames: list[dict[str, str]]
    ) -> dict[str, Any]:
        """Synchronous version of ``rename_batch_jobs()``."""
        return self._request_sync(
            "PATCH", f"/batch/{batch_id}/jobs", json={"renames": renames}
        )

    def sync_wait_for_batch(
        self,
        batch_id: str,
        *,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
        not_found_grace_period: float = 30.0,
    ) -> BatchJob:
        """Synchronous version of ``wait_for_batch()``.

        Blocks the current thread until all batch episodes reach a terminal state.
        """
        start_t = time.monotonic()
        while True:
            try:
                batch = self.sync_get_batch(batch_id)
            except NotFoundError:
                if (time.monotonic() - start_t) < not_found_grace_period:
                    time.sleep(poll_interval)
                    continue
                raise
            if batch.is_terminal:
                return batch
            if batch.done_episodes >= batch.total_episodes and batch.total_episodes > 0:
                return batch
            if timeout is not None and (time.monotonic() - start_t) >= timeout:
                raise TimeoutError(
                    f"Batch {batch_id} did not complete within {timeout}s"
                )
            time.sleep(poll_interval)

    # -- Storage configuration sync wrappers ----------------------------------

    def sync_configure_s3(self, config: S3StorageConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_s3()``."""
        return self._request_sync("POST", "/user/s3", json=config.to_dict())

    def sync_delete_s3(self) -> dict[str, Any]:
        """Synchronous version of ``delete_s3()``."""
        return self._request_sync("DELETE", "/user/s3")

    def sync_get_s3(self) -> dict[str, Any]:
        """Synchronous version of ``get_s3()``."""
        return self._request_sync("GET", "/user/s3")

    def sync_configure_blob(self, config: BlobStorageConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_blob()``."""
        return self._request_sync("POST", "/user/blob", json=config.to_dict())

    def sync_delete_blob(self) -> dict[str, Any]:
        """Synchronous version of ``delete_blob()``."""
        return self._request_sync("DELETE", "/user/blob")

    def sync_configure_gcs(self, config: GcsStorageConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_gcs()``."""
        return self._request_sync("POST", "/user/gcs", json=config.to_dict())

    def sync_delete_gcs(self) -> dict[str, Any]:
        """Synchronous version of ``delete_gcs()``."""
        return self._request_sync("DELETE", "/user/gcs")

    def sync_configure_gdrive(self, config: GDriveStorageConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_gdrive()``."""
        return self._request_sync("POST", "/user/gdrive", json=config.to_dict())

    def sync_delete_gdrive(self) -> dict[str, Any]:
        """Synchronous version of ``delete_gdrive()``."""
        return self._request_sync("DELETE", "/user/gdrive")

    def sync_configure_oss(self, config: OssStorageConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_oss()``."""
        return self._request_sync("POST", "/user/oss", json=config.to_dict())

    def sync_delete_oss(self) -> dict[str, Any]:
        """Synchronous version of ``delete_oss()``."""
        return self._request_sync("DELETE", "/user/oss")

    def sync_configure_bucket(
        self,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> dict[str, Any]:
        """Synchronous version of ``configure_bucket()`` (legacy S3 endpoint)."""
        return self._request_sync(
            "POST",
            "/user/bucket",
            json={
                "endpoint": endpoint,
                "bucket": bucket,
                "region": region,
                "access_key": access_key,
                "secret_key": secret_key,
            },
        )

    def sync_delete_bucket(self) -> dict[str, Any]:
        """Synchronous version of ``delete_bucket()``."""
        return self._request_sync("DELETE", "/user/bucket")

    def sync_configure_slack(self, config: SlackWebhookConfig) -> dict[str, Any]:
        """Synchronous version of ``configure_slack()``."""
        return self._request_sync("POST", "/user/slack", json=config.to_dict())

    def sync_delete_slack(self) -> dict[str, Any]:
        """Synchronous version of ``delete_slack()``."""
        return self._request_sync("DELETE", "/user/slack")

    def sync_get_webhook_secret(self) -> str:
        """Synchronous version of ``get_webhook_secret()``. Returns the secret."""
        data = self._request_sync("GET", "/user/webhook-secret")
        return data.get("webhook_signing_secret", "")

    def sync_rotate_webhook_secret(self) -> str:
        """Synchronous version of ``rotate_webhook_secret()``. Returns the NEW secret."""
        data = self._request_sync("POST", "/user/webhook-secret/rotate")
        return data.get("webhook_signing_secret", "")
