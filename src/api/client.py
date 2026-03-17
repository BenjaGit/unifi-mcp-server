"""UniFi API client with authentication, rate limiting, and error handling."""

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import APIType, Settings
from ..utils import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ResourceNotFoundError,
    get_logger,
    log_api_request,
)


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_period: int, period_seconds: int) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_period: Maximum requests allowed in the period
            period_seconds: Time period in seconds
        """
        self.requests_per_period = requests_per_period
        self.period_seconds = period_seconds
        self.tokens: float = float(requests_per_period)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens = min(
                self.requests_per_period,
                self.tokens + (time_passed * self.requests_per_period / self.period_seconds),
            )
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) * self.period_seconds / self.requests_per_period
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class UniFiClient:
    """Async HTTP client for UniFi API with authentication and rate limiting."""

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        """Initialize UniFi API client.

        Args:
            settings: Application settings
            api_key: Specific API key to use. If None, uses settings default.
        """
        self.settings = settings
        self.logger = get_logger(__name__, settings.log_level)

        # Initialize HTTP client
        # Note: We construct full URLs explicitly in _request() to ensure HTTPS is preserved
        # Using base_url can cause protocol downgrade issues with httpx
        self.client = httpx.AsyncClient(
            headers=settings.get_headers(api_key),
            timeout=settings.request_timeout,
            verify=settings.verify_ssl,
            follow_redirects=False,  # Prevent HTTP redirects that might downgrade protocol
        )

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            settings.rate_limit_requests,
            settings.rate_limit_period,
        )

        self._authenticated = False

    async def __aenter__(self) -> "UniFiClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        return self._authenticated

    async def authenticate(self) -> None:
        """Authenticate with the UniFi API.

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # Test authentication with a simple API call
            # Use appropriate endpoint based on API type
            if self.settings.api_type == APIType.CLOUD_V1:
                test_endpoint = "/v1/hosts"  # V1 stable API
            else:
                test_endpoint = "/ea/sites"  # EA API or local (will be auto-translated)

            response = await self._request("GET", test_endpoint, allow_reauth=False)

            # Handle both dict and list responses
            # Local API (after normalization) returns list directly
            # Cloud API returns dict with "meta", "data", etc.
            if isinstance(response, list):
                # List response means we got data successfully (local API)
                self._authenticated = True
            elif isinstance(response, dict):
                # Dict response - check for success indicators
                self._authenticated = (
                    response.get("meta", {}).get("rc") == "ok"
                    or response.get("data") is not None
                    or response.get("count") is not None
                )
            else:
                self._authenticated = False

            self.logger.info(
                f"Successfully authenticated with UniFi API (response type: {type(response).__name__})"
            )
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with UniFi API: {e}") from e

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry_count: int = 0,
        allow_reauth: bool = True,
    ) -> Any:
        """Make an HTTP request with retries and error handling."""

        try:
            return await self._perform_request(method, endpoint, params, json_data, retry_count)
        except AuthenticationError:
            if not allow_reauth:
                raise
            await self.authenticate()
            return await self._perform_request(method, endpoint, params, json_data, retry_count)

    async def _perform_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> Any:
        """Make an HTTP request with retries and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt number

        Returns:
            Response data as dictionary

        Raises:
            APIError: If API returns an error
            RateLimitError: If rate limit is exceeded
            NetworkError: If network communication fails
        """
        # Apply rate limiting
        await self.rate_limiter.acquire()

        start_time = time.time()

        try:
            allowed_host = urlparse(self.settings.base_url).hostname
            parsed_endpoint = urlparse(endpoint)

            # Allow absolute URLs only when they target the configured UniFi host.
            if parsed_endpoint.scheme or parsed_endpoint.netloc:
                endpoint_host = parsed_endpoint.hostname
                if (
                    not allowed_host
                    or not endpoint_host
                    or endpoint_host.lower() != allowed_host.lower()
                ):
                    raise APIError(
                        f"Blocked request to untrusted host in endpoint: {endpoint}",
                    )

            # Construct full URL explicitly to ensure HTTPS protocol is preserved
            # httpx's base_url joining can have issues with protocol handling
            full_url = (
                f"{self.settings.base_url}{endpoint}" if endpoint.startswith("/") else endpoint
            )

            # CRITICAL: Ensure HTTPS scheme - force replace http:// with https://
            if full_url.startswith("http://"):
                full_url = full_url.replace("http://", "https://", 1)
                self.logger.warning(f"Force-corrected HTTP to HTTPS: {full_url}")

            # ENHANCED LOGGING - Show actual URL being requested
            self.logger.info(f"Making {method} request to: {full_url}")

            response = await self.client.request(
                method=method,
                url=full_url,
                params=params,
                json=json_data,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Log request if enabled
            if self.settings.log_api_requests:
                log_api_request(
                    self.logger,
                    method=method,
                    url=endpoint,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))

                # Retry if we haven't exceeded max retries
                if retry_count < self.settings.max_retries:
                    self.logger.warning(f"Rate limited, retrying after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return await self._perform_request(
                        method, endpoint, params, json_data, retry_count + 1
                    )

                raise RateLimitError(retry_after=retry_after)

            # Handle not found
            if response.status_code == 404:
                raise ResourceNotFoundError("resource", endpoint)

            # Handle authentication errors
            if response.status_code in (401, 403):
                raise AuthenticationError(f"Authentication failed: {response.text}")

            # Handle other errors
            if response.status_code >= 400:
                error_data = None
                try:
                    error_data = response.json()
                except Exception:
                    pass

                raise APIError(
                    message=f"API request failed: {response.text}",
                    status_code=response.status_code,
                    response_data=error_data,
                )

            # Parse response - handle empty responses from local gateway
            try:
                if response.text and response.text.strip():
                    json_response: dict[str, Any] = response.json()

                    # Normalize response format based on API type
                    # Cloud V1 API returns: {"data": [...], "httpStatusCode": 200, "traceId": "..."}
                    # Local API returns: {"data": [...], "count": N, "totalCount": N}
                    # Cloud EA API returns: {...} or [...] directly
                    if isinstance(json_response, dict) and "data" in json_response:
                        # Both cloud v1 and local API wrap data in a "data" field
                        data = json_response["data"]
                        api_type = (
                            self.settings.api_type.value
                            if hasattr(self.settings.api_type, "value")
                            else str(self.settings.api_type)
                        )
                        self.logger.debug(
                            f"Normalized {api_type} API response: extracted {len(data) if isinstance(data, list) else 'N/A'} items"
                        )
                        # Return the data directly for consistency across all APIs
                        # If data is a list, return it; if single object, return as-is
                        return data if isinstance(data, list) else {"data": data}
                else:
                    # Empty response body - treat as success with empty data
                    self.logger.debug(f"Empty response body for {endpoint}, returning empty dict")
                    json_response = {}
                return json_response
            except (ValueError, json.JSONDecodeError) as e:
                # Invalid JSON - log and return empty dict for successful status codes
                self.logger.warning(f"Invalid JSON in response for {endpoint}: {e}")
                return {}

        except httpx.TimeoutException as e:
            # Retry on timeout
            if retry_count < self.settings.max_retries:
                backoff = self.settings.retry_backoff_factor**retry_count
                self.logger.warning(f"Request timeout, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                return await self._perform_request(
                    method, endpoint, params, json_data, retry_count + 1
                )

            raise NetworkError(f"Request timeout: {e}") from e

        except httpx.NetworkError as e:
            # Retry on network error
            if retry_count < self.settings.max_retries:
                backoff = self.settings.retry_backoff_factor**retry_count
                self.logger.warning(f"Network error, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                return await self._perform_request(
                    method, endpoint, params, json_data, retry_count + 1
                )

            raise NetworkError(f"Network communication failed: {e}") from e

        except (RateLimitError, AuthenticationError, APIError, ResourceNotFoundError):
            # Re-raise our custom exceptions
            raise

        except Exception as e:
            self.logger.error(f"Unexpected error during API request: {e}")
            raise APIError(f"Unexpected error: {e}") from e

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("POST", endpoint, params=params, json_data=json_data)

    async def put(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("PUT", endpoint, params=params, json_data=json_data)

    async def delete(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response data
        """
        return await self._request("DELETE", endpoint, params=params)
