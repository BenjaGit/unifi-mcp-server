"""Unit tests for site management tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.sites as sites_module
from src.api.network_client import SiteInfo
from src.tools.sites import get_site_details, get_site_statistics, list_sites
from src.utils.exceptions import ResourceNotFoundError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_site_details_success() -> None:
    client = _make_client()
    client.get.return_value = [
        {"_id": "site-123", "name": "Default", "desc": "Main site"},
        {"_id": "site-456", "name": "Branch", "desc": "Branch Office"},
    ]

    with patch.object(sites_module, "get_network_client", return_value=client):
        result = await get_site_details("site-123")

    assert result["id"] == "site-123"
    assert result["name"] == "Default"


@pytest.mark.asyncio
async def test_get_site_details_not_found() -> None:
    client = _make_client()
    client.get.return_value = [{"_id": "site-abc", "name": "OtherSite", "desc": "Another site"}]

    with patch.object(sites_module, "get_network_client", return_value=client):
        with pytest.raises(ResourceNotFoundError):
            await get_site_details("nonexistent-site")


@pytest.mark.asyncio
async def test_list_sites_with_limit_offset() -> None:
    client = _make_client()
    client.get.return_value = [
        {"_id": "site-0", "name": "Site0", "desc": "First"},
        {"_id": "site-1", "name": "Site1", "desc": "Second"},
        {"_id": "site-2", "name": "Site2", "desc": "Third"},
    ]

    with patch.object(sites_module, "get_network_client", return_value=client):
        result = await list_sites(limit=2, offset=1)

    assert len(result) == 2
    assert result[0]["id"] == "site-1"


@pytest.mark.asyncio
async def test_list_sites_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = []

    with patch.object(sites_module, "get_network_client", return_value=client):
        await list_sites()

    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_site_statistics_success() -> None:
    client = _make_client()
    client.get = AsyncMock(
        side_effect=[
            [{"_id": "ap1", "type": "uap", "state": 1}],
            [{"mac": "aa:bb", "is_wired": True, "tx_bytes": 100, "rx_bytes": 200}],
            [{"_id": "net1", "name": "LAN"}],
        ]
    )

    with patch.object(sites_module, "get_network_client", return_value=client):
        result = await get_site_statistics("default")

    assert result["devices"]["total"] == 1
    assert result["clients"]["total"] == 1
    assert result["networks"]["total"] == 1
    assert result["bandwidth"]["total_bytes"] == 300
