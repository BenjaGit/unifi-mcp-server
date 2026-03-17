"""Unit tests for UniFi API client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.api.client import RateLimiter, UniFiClient
from src.config import APIType
from src.utils.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ResourceNotFoundError,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = APIType.CLOUD_EA
    settings.base_url = "https://api.ui.com"
    settings.network_api_key = "test-api-key"
    settings.request_timeout = 30.0
    settings.verify_ssl = True
    settings.rate_limit_requests = 100
    settings.rate_limit_period = 60
    settings.max_retries = 3
    settings.retry_backoff_factor = 2
    settings.log_api_requests = True
    settings.default_site = "default"
    settings.get_headers = MagicMock(return_value={"X-API-Key": "test-api-key"})
    return settings


@pytest.fixture
def mock_settings_local():
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.api_type = APIType.LOCAL
    settings.base_url = "https://192.168.2.1"
    settings.network_api_key = "test-api-key"
    settings.request_timeout = 30.0
    settings.verify_ssl = False
    settings.rate_limit_requests = 100
    settings.rate_limit_period = 60
    settings.max_retries = 3
    settings.retry_backoff_factor = 2
    settings.log_api_requests = True
    settings.default_site = "default"
    settings.get_headers = MagicMock(return_value={"X-API-Key": "test-api-key"})
    return settings


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        limiter = RateLimiter(requests_per_period=10, period_seconds=60)

        for _ in range(5):
            await limiter.acquire()

        assert limiter.tokens >= 4

    @pytest.mark.asyncio
    async def test_acquire_depletes_tokens(self):
        limiter = RateLimiter(requests_per_period=5, period_seconds=60)
        initial_tokens = limiter.tokens

        await limiter.acquire()
        assert limiter.tokens < initial_tokens

        await limiter.acquire()
        assert limiter.tokens < initial_tokens - 1

    @pytest.mark.asyncio
    async def test_acquire_waits_when_exhausted(self):
        limiter = RateLimiter(requests_per_period=100, period_seconds=1)
        limiter.tokens = 0.0

        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        duration = asyncio.get_event_loop().time() - start

        assert duration >= 0.001


class TestUniFiClientInit:
    @pytest.mark.asyncio
    async def test_client_init(self, mock_settings):
        client = UniFiClient(mock_settings)

        assert client.settings == mock_settings
        assert client._authenticated is False
        await client.close()

    @pytest.mark.asyncio
    async def test_client_context_manager(self, mock_settings):
        async with UniFiClient(mock_settings) as client:
            assert client is not None
            assert isinstance(client, UniFiClient)

    @pytest.mark.asyncio
    async def test_is_authenticated_property(self, mock_settings):
        client = UniFiClient(mock_settings)

        assert client.is_authenticated is False
        client._authenticated = True
        assert client.is_authenticated is True

        await client.close()


class TestUniFiClientAuthentication:
    @pytest.mark.asyncio
    async def test_authenticate_success_list_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"id": "site1"}]'
        mock_response.json = MagicMock(return_value=[{"id": "site1"}])

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.authenticate()

        assert client._authenticated is True
        await client.close()

    @pytest.mark.asyncio
    async def test_authenticate_success_dict_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "site1"}]}'
        mock_response.json = MagicMock(return_value={"data": [{"id": "site1"}]})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.authenticate()

        assert client._authenticated is True
        await client.close()

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_settings):
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Connection refused")

            with pytest.raises(AuthenticationError, match="Failed to authenticate"):
                await client.authenticate()

        await client.close()


class TestUniFiClientHttpMethods:
    @pytest.mark.asyncio
    async def test_get_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": [{"id": "device1"}]}'
        mock_response.json = MagicMock(return_value={"data": [{"id": "device1"}]})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites/default/devices")

        assert result == [{"id": "device1"}]
        await client.close()

    @pytest.mark.asyncio
    async def test_post_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": {"id": "new-resource"}}'
        mock_response.json = MagicMock(return_value={"data": {"id": "new-resource"}})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.post("/ea/sites/default/networks", {"name": "test"})

        assert result == {"data": {"id": "new-resource"}}
        await client.close()

    @pytest.mark.asyncio
    async def test_put_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": {"id": "updated"}}'
        mock_response.json = MagicMock(return_value={"data": {"id": "updated"}})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.put("/ea/sites/default/networks/123", {"name": "updated"})

        assert result == {"data": {"id": "updated"}}
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "{}"
        mock_response.json = MagicMock(return_value={})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.delete("/ea/sites/default/networks/123")

        assert result == {}
        await client.close()


class TestAuthRetry:
    @pytest.mark.asyncio
    async def test_reauth_on_auth_error(self, mock_settings):
        client = UniFiClient(mock_settings)

        auth_failure = MagicMock()
        auth_failure.status_code = 401
        auth_failure.text = "unauthorized"
        auth_failure.json = MagicMock(return_value={})

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.text = '{"data": []}'
        success_response.json = MagicMock(return_value={"data": []})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [auth_failure, success_response]
            client.authenticate = AsyncMock()

            result = await client.get("/ea/sites/default/devices")

        client.authenticate.assert_awaited_once()
        assert mock_request.await_count == 2
        assert result == []
        await client.close()

    @pytest.mark.asyncio
    async def test_reauth_failure_propagates(self, mock_settings):
        client = UniFiClient(mock_settings)

        auth_failure = MagicMock()
        auth_failure.status_code = 401
        auth_failure.text = "unauthorized"
        auth_failure.json = MagicMock(return_value={})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [auth_failure, auth_failure]
            client.authenticate = AsyncMock()

            with pytest.raises(AuthenticationError):
                await client.get("/ea/sites/default/devices")

        client.authenticate.assert_awaited_once()
        assert mock_request.await_count == 2
        await client.close()


class TestUniFiClientErrorHandling:
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_settings):
        mock_settings.max_retries = 0
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(RateLimitError):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_not_found_error(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ResourceNotFoundError):
                await client.get("/ea/sites/nonexistent")

        await client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_401(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_authentication_error_403(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_api_error(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json = MagicMock(return_value={"error": "Server error"})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(APIError, match="API request failed"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_retry(self, mock_settings):
        mock_settings.max_retries = 2
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("timeout")
            return mock_response

        with patch.object(client.client, "request", side_effect=side_effect):
            result = await client.get("/ea/sites")

        assert result == []
        assert call_count == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_max_retries_exceeded(self, mock_settings):
        mock_settings.max_retries = 1
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = httpx.TimeoutException("timeout")

            with pytest.raises(NetworkError, match="timeout"):
                await client.get("/ea/sites")

        await client.close()

    @pytest.mark.asyncio
    async def test_network_error_retry(self, mock_settings):
        mock_settings.max_retries = 2
        mock_settings.retry_backoff_factor = 0.01
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.NetworkError("connection reset")
            return mock_response

        with patch.object(client.client, "request", side_effect=side_effect):
            result = await client.get("/ea/sites")

        assert result == []
        assert call_count == 2
        await client.close()


class TestUniFiClientResponseParsing:
    @pytest.mark.anyio
    async def test_blocks_absolute_external_url(self, mock_settings):
        client = UniFiClient(mock_settings)

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            with pytest.raises(APIError, match="Blocked request to untrusted host"):
                await client.get("https://example.com/ea/sites")

            mock_request.assert_not_called()

        await client.close()

    @pytest.mark.anyio
    async def test_allows_absolute_url_for_configured_host(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("https://api.ui.com/ea/sites")

            assert result == []
            call_args = mock_request.call_args
            assert call_args[1]["url"] == "https://api.ui.com/ea/sites"

        await client.close()

    @pytest.mark.asyncio
    async def test_parse_empty_response(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.json = MagicMock(return_value={})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites/default/some-endpoint")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self, mock_settings):
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not json"
        mock_response.json = MagicMock(side_effect=ValueError("Invalid JSON"))

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get("/ea/sites")

        assert result == {}
        await client.close()

    @pytest.mark.asyncio
    async def test_https_force_correction(self, mock_settings):
        mock_settings.base_url = "http://api.ui.com"
        client = UniFiClient(mock_settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"data": []}'
        mock_response.json = MagicMock(return_value={"data": []})

        with patch.object(client.client, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await client.get("/ea/sites")

            call_args = mock_request.call_args
            assert call_args[1]["url"].startswith("https://")

        await client.close()
