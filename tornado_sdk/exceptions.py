"""
Exception hierarchy for the Tornado SDK.

All exceptions inherit from TornadoError. API-level errors (HTTP responses)
inherit from TornadoAPIError which carries the status_code and response body.

Hierarchy:
    TornadoError
    └── TornadoAPIError (has status_code, response_body)
        ├── AuthenticationError  (401, 403)
        ├── RateLimitError       (429, has retry_after)
        ├── NotFoundError        (404)
        └── ValidationError      (400)
"""

from __future__ import annotations

from typing import Any, Optional


class TornadoError(Exception):
    """Base exception for all Tornado SDK errors.

    This covers both local SDK errors (e.g., invalid arguments) and
    remote API errors. Catch this to handle any SDK-related failure.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TornadoAPIError(TornadoError):
    """Error returned by the Tornado API as an HTTP response.

    Attributes:
        status_code: HTTP status code (e.g., 400, 401, 404, 429, 500).
        response_body: Parsed JSON response body from the API.
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body or {}
        super().__init__(message)

    def __str__(self) -> str:
        return f"[HTTP {self.status_code}] {self.message}"


class AuthenticationError(TornadoAPIError):
    """Raised when the API key is invalid, missing, or lacks permission.

    HTTP status: 401 (Unauthorized) or 403 (Forbidden).
    Common causes: expired key, wrong key, IP restriction, quota exceeded.
    """

    def __init__(
        self,
        message: str = "Invalid or missing API key",
        status_code: int = 401,
        response_body: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, status_code, response_body)


class RateLimitError(TornadoAPIError):
    """Raised when the server is at capacity or rate limit is exceeded.

    HTTP status: 429 (Too Many Requests).
    The ``retry_after`` attribute indicates how many seconds to wait
    before retrying. The client's built-in retry logic handles this
    automatically when max_retries > 0.

    Attributes:
        retry_after: Suggested wait time in seconds (from Retry-After header).
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        status_code: int = 429,
        response_body: Optional[dict[str, Any]] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code, response_body)


class NotFoundError(TornadoAPIError):
    """Raised when the requested resource does not exist.

    HTTP status: 404 (Not Found).
    Common causes: invalid job_id, expired job (TTL 24h), wrong batch_id.
    """

    def __init__(
        self,
        message: str = "Resource not found",
        status_code: int = 404,
        response_body: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, status_code, response_body)


class ValidationError(TornadoAPIError):
    """Raised when request validation fails on the server side.

    HTTP status: 400 (Bad Request).
    Common causes: invalid URL, unsupported format, path traversal in folder name.
    """

    def __init__(
        self,
        message: str = "Invalid request",
        status_code: int = 400,
        response_body: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, status_code, response_body)
