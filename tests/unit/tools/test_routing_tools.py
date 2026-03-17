"""Unit tests for routing tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.routing as routing_module
from src.api.network_client import SiteInfo
from src.tools.routing import get_ddns_status, list_active_routes
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_ddns_status_basic() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"service": "dyndns", "hostname": "home.example.com", "status": "ok"},
            {"service": "duckdns", "hostname": "myplace.duckdns.org", "status": "ok"},
        ]
    }

    with patch.object(routing_module, "get_network_client", return_value=client):
        result = await get_ddns_status("default")

    assert result["count"] == 2
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/stat/dynamicdns")


@pytest.mark.asyncio
async def test_get_ddns_status_invalid_site_id() -> None:
    with pytest.raises((ValidationError, Exception)):
        await get_ddns_status("")


@pytest.mark.asyncio
async def test_list_active_routes_basic() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"pfx": "0.0.0.0/0", "nh": [{"via": "192.168.1.1"}]},
            {"pfx": "192.168.1.0/24", "nh": [{"intf": "eth0"}]},
        ]
    }

    with patch.object(routing_module, "get_network_client", return_value=client):
        result = await list_active_routes("default")

    assert result["count"] == 2
    assert "pfx" in result["routes"][0]


@pytest.mark.asyncio
async def test_list_active_routes_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(routing_module, "get_network_client", return_value=client):
        await list_active_routes("default")

    client.authenticate.assert_awaited_once()
