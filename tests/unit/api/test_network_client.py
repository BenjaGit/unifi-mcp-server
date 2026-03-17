"""Tests for NetworkClient path building and site resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.network_client import NetworkClient, SiteInfo
from src.config import APIType


@pytest.fixture
def _base_settings():
    """Shared settings fields."""
    settings = MagicMock()
    settings.log_level = "INFO"
    settings.network_api_key = "test-key"
    settings.default_site = "default"
    settings.request_timeout = 30
    settings.verify_ssl = False
    settings.rate_limit_requests = 100
    settings.rate_limit_period = 60
    settings.log_api_requests = False
    settings.max_retries = 0
    settings.retry_backoff_factor = 2.0
    return settings


@pytest.fixture
def mock_settings_local(_base_settings):
    _base_settings.api_type = APIType.LOCAL
    _base_settings.base_url = "https://192.168.2.1:443"
    _base_settings.local_host = "192.168.2.1"
    _base_settings.local_port = 443
    _base_settings.local_verify_ssl = False
    return _base_settings


@pytest.fixture
def mock_settings_cloud_ea(_base_settings):
    _base_settings.api_type = APIType.CLOUD_EA
    _base_settings.base_url = "https://api.ui.com"
    return _base_settings


@pytest.fixture
def mock_settings_cloud_v1(_base_settings):
    _base_settings.api_type = APIType.CLOUD_V1
    _base_settings.base_url = "https://api.ui.com"
    return _base_settings


# ── Path building tests ─────────────────────────────────────────────


class TestLegacyPath:
    """Test legacy_path() across all API modes."""

    def test_local_rest_firewallrule(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "rest/firewallrule") == (
            "/proxy/network/api/s/default/rest/firewallrule"
        )

    def test_local_stat_device(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "stat/device") == (
            "/proxy/network/api/s/default/stat/device"
        )

    def test_local_cmd_backup(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "cmd/backup") == (
            "/proxy/network/api/s/default/cmd/backup"
        )

    def test_cloud_ea_rest_firewallrule(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.legacy_path("site-uuid-123", "rest/firewallrule") == (
            "/ea/sites/site-uuid-123/rest/firewallrule"
        )

    def test_local_sta_maps_to_stat_sta(self, mock_settings_local):
        """Local API uses stat/sta for active clients, not bare sta."""
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "sta") == ("/proxy/network/api/s/default/stat/sta")

    def test_local_devices_maps_to_stat_device(self, mock_settings_local):
        """Local API uses stat/device for devices, not bare devices."""
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "devices") == (
            "/proxy/network/api/s/default/stat/device"
        )

    def test_cloud_ea_sta_unchanged(self, mock_settings_cloud_ea):
        """Cloud EA uses bare sta (no mapping)."""
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.legacy_path("abc123", "sta") == "/ea/sites/abc123/sta"

    def test_cloud_ea_devices(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.legacy_path("abc123", "devices") == "/ea/sites/abc123/devices"

    def test_cloud_v1_rest_firewallrule(self, mock_settings_cloud_v1):
        client = NetworkClient(mock_settings_cloud_v1)
        assert client.legacy_path("anything", "rest/firewallrule") == ("/v1/rest/firewallrule")

    def test_strips_leading_slash(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.legacy_path("default", "/rest/firewallrule") == (
            "/proxy/network/api/s/default/rest/firewallrule"
        )


class TestIntegrationPath:
    """Test integration_path() across all API modes."""

    def test_local_firewall_zones(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.integration_path("uuid-123", "firewall/zones") == (
            "/proxy/network/integration/v1/sites/uuid-123/firewall/zones"
        )

    def test_cloud_ea_firewall_zones(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.integration_path("uuid-123", "firewall/zones") == (
            "/integration/v1/sites/uuid-123/firewall/zones"
        )

    def test_cloud_v1_firewall_zones(self, mock_settings_cloud_v1):
        client = NetworkClient(mock_settings_cloud_v1)
        assert client.integration_path("uuid-123", "firewall/zones") == (
            "/v1/sites/uuid-123/firewall/zones"
        )

    def test_local_networks(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.integration_path("uuid-123", "networks") == (
            "/proxy/network/integration/v1/sites/uuid-123/networks"
        )

    def test_strips_leading_slash(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.integration_path("uuid-123", "/clients") == (
            "/integration/v1/sites/uuid-123/clients"
        )


class TestIntegrationBasePath:
    """Test integration_base_path() for site-less endpoints."""

    def test_local_sites(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.integration_base_path("sites") == ("/proxy/network/integration/v1/sites")

    def test_cloud_ea_sites(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        assert client.integration_base_path("sites") == "/integration/v1/sites"

    def test_cloud_v1_sites(self, mock_settings_cloud_v1):
        client = NetworkClient(mock_settings_cloud_v1)
        assert client.integration_base_path("sites") == "/v1/sites"


class TestV2Path:
    """Test v2_path() for local-only endpoints."""

    def test_local_firewall_policies(self, mock_settings_local):
        client = NetworkClient(mock_settings_local)
        assert client.v2_path("default", "firewall/policies") == (
            "/proxy/network/v2/api/site/default/firewall/policies"
        )

    def test_cloud_ea_raises(self, mock_settings_cloud_ea):
        client = NetworkClient(mock_settings_cloud_ea)
        with pytest.raises(NotImplementedError):
            client.v2_path("default", "firewall/policies")

    def test_cloud_v1_raises(self, mock_settings_cloud_v1):
        client = NetworkClient(mock_settings_cloud_v1)
        with pytest.raises(NotImplementedError):
            client.v2_path("default", "firewall/policies")


# ── Site resolution tests ────────────────────────────────────────────


class TestResolveSite:
    """Test resolve_site() returns correct SiteInfo."""

    @pytest.mark.asyncio
    async def test_resolve_by_name(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(
                return_value=[
                    {
                        "id": "88f7af54-abcd-1234-ef56-789012345678",
                        "internalReference": "default",
                        "name": "Default",
                    }
                ]
            )

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            site = await client.resolve_site("default")
            assert site.name == "default"
            assert site.uuid == "88f7af54-abcd-1234-ef56-789012345678"

    @pytest.mark.asyncio
    async def test_resolve_by_uuid(self, mock_settings_cloud_ea):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(
                return_value=[
                    {
                        "id": "88f7af54-abcd-1234-ef56-789012345678",
                        "internalReference": "default",
                        "name": "Default",
                    }
                ]
            )

            client = NetworkClient(mock_settings_cloud_ea)
            client._client = mock_inner

            site = await client.resolve_site("88f7af54-abcd-1234-ef56-789012345678")
            assert site.name == "default"
            assert site.uuid == "88f7af54-abcd-1234-ef56-789012345678"

    @pytest.mark.asyncio
    async def test_resolve_default_when_none(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(
                return_value=[
                    {
                        "id": "uuid-default",
                        "internalReference": "default",
                        "name": "Default",
                    }
                ]
            )

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            site = await client.resolve_site(None)
            assert site.name == "default"

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(return_value=[])

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            with pytest.raises(Exception, match="not found"):
                await client.resolve_site("nonexistent")

    @pytest.mark.asyncio
    async def test_resolve_caches_result(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(
                return_value=[
                    {
                        "id": "uuid-123",
                        "internalReference": "default",
                        "name": "Default",
                    }
                ]
            )

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            site1 = await client.resolve_site("default")
            site2 = await client.resolve_site("default")

            assert site1 == site2
            # Should only call API once due to cache
            assert mock_inner.get.call_count == 1

    @pytest.mark.asyncio
    async def test_resolve_dict_response(self, mock_settings_cloud_ea):
        """Test resolve_site handles dict responses with 'data' key."""
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()
            mock_inner.is_authenticated = True
            mock_inner.get = AsyncMock(
                return_value={
                    "data": [
                        {
                            "id": "uuid-456",
                            "internalReference": "mysite",
                            "name": "My Site",
                        }
                    ]
                }
            )

            client = NetworkClient(mock_settings_cloud_ea)
            client._client = mock_inner

            site = await client.resolve_site("mysite")
            assert site.name == "mysite"
            assert site.uuid == "uuid-456"


# ── Context manager and delegation tests ─────────────────────────────


class TestContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.__aenter__ = AsyncMock(return_value=mock_inner)
            mock_inner.__aexit__ = AsyncMock()

            async with NetworkClient(mock_settings_local) as client:
                assert client is not None

            mock_inner.__aenter__.assert_called_once()
            mock_inner.__aexit__.assert_called_once()


class TestHTTPDelegation:
    @pytest.mark.asyncio
    async def test_get_delegates(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.get = AsyncMock(return_value={"data": []})

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            await client.get("/test")
            mock_inner.get.assert_called_once_with("/test", params=None)

    @pytest.mark.asyncio
    async def test_post_delegates(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.post = AsyncMock(return_value={})

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            await client.post("/test", json_data={"key": "val"})
            mock_inner.post.assert_called_once_with("/test", json_data={"key": "val"}, params=None)

    @pytest.mark.asyncio
    async def test_put_delegates(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.put = AsyncMock(return_value={})

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            await client.put("/test", json_data={"key": "val"})
            mock_inner.put.assert_called_once_with("/test", json_data={"key": "val"}, params=None)

    @pytest.mark.asyncio
    async def test_delete_delegates(self, mock_settings_local):
        with patch("src.api.network_client.UniFiClient") as MockClient:
            mock_inner = AsyncMock()
            MockClient.return_value = mock_inner
            mock_inner.delete = AsyncMock(return_value={})

            client = NetworkClient(mock_settings_local)
            client._client = mock_inner

            await client.delete("/test")
            mock_inner.delete.assert_called_once_with("/test", params=None)


class TestSiteInfoDataclass:
    def test_frozen(self):
        info = SiteInfo(name="default", uuid="uuid-123")
        with pytest.raises(AttributeError):
            info.name = "changed"

    def test_equality(self):
        a = SiteInfo(name="default", uuid="uuid-123")
        b = SiteInfo(name="default", uuid="uuid-123")
        assert a == b

    def test_fields(self):
        info = SiteInfo(name="default", uuid="uuid-123")
        assert info.name == "default"
        assert info.uuid == "uuid-123"
