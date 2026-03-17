"""Unit tests for site health and system info tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.health as health_module
from src.api.network_client import SiteInfo
from src.tools.health import get_site_health, get_system_info
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    return client


SAMPLE_HEALTH = [
    {"subsystem": "wlan", "num_user": 57, "status": "ok"},
    {"subsystem": "wan", "isp_name": "TDC NET", "status": "ok"},
]

SAMPLE_SYSINFO = {
    "timezone": "Europe/Copenhagen",
    "version": "10.1.85",
    "hostname": "Coldberg-UDM-Pro-Max",
}


@pytest.mark.asyncio
async def test_get_site_health_basic() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_HEALTH}

    with patch.object(health_module, "get_network_client", return_value=client):
        result = await get_site_health("default")

    assert result["count"] == 2
    assert result["site_id"] == "default"
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/stat/health")


@pytest.mark.asyncio
async def test_get_site_health_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(health_module, "get_network_client", return_value=client):
        await get_site_health("default")

    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_site_health_invalid_site_id() -> None:
    with pytest.raises((ValidationError, Exception)):
        await get_site_health("")


@pytest.mark.asyncio
async def test_get_system_info_basic() -> None:
    client = _make_client()
    client.get.return_value = {"data": [SAMPLE_SYSINFO]}

    with patch.object(health_module, "get_network_client", return_value=client):
        result = await get_system_info("default")

    assert result["version"] == "10.1.85"
    assert result["hostname"] == "Coldberg-UDM-Pro-Max"
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/stat/sysinfo")


@pytest.mark.asyncio
async def test_get_system_info_empty_response() -> None:
    client = _make_client()
    client.get.return_value = {"data": []}

    with patch.object(health_module, "get_network_client", return_value=client):
        result = await get_system_info("default")

    assert result == {}
