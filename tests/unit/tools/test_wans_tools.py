"""Unit tests for WAN tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.wans as wans_module
from src.api.network_client import SiteInfo
from src.tools.wans import list_wan_connections


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.integration_path = MagicMock(
        side_effect=lambda site_uuid, ep: f"/integration/v1/sites/{site_uuid}/{ep}"
    )
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_wan_connections_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {
                "id": "wan-1",
                "name": "WAN 1",
                "wanType": "DHCP",
                "uplinkType": "ethernet",
                "enabled": True,
            }
        ]
    }

    with patch.object(wans_module, "get_network_client", return_value=client):
        result = await list_wan_connections("default")

    assert len(result) == 1
    assert result[0]["id"] == "wan-1"


@pytest.mark.asyncio
async def test_list_wan_connections_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(wans_module, "get_network_client", return_value=client):
        result = await list_wan_connections("default")

    assert result == []
    client.authenticate.assert_awaited_once()
