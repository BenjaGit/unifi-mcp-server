"""Unit tests for site-to-site VPN tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.site_vpn as vpn_module
from src.api.network_client import SiteInfo
from src.tools.site_vpn import get_site_to_site_vpn, list_site_to_site_vpns, update_site_to_site_vpn
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.put = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_site_to_site_vpns_filters_purpose() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "vpn1", "name": "S2S", "purpose": "site-vpn", "enabled": True},
            {"_id": "net1", "name": "LAN", "purpose": "corporate"},
        ]
    }

    with patch.object(vpn_module, "get_network_client", return_value=client):
        result = await list_site_to_site_vpns("default")

    assert len(result) == 1
    assert result[0]["id"] == "vpn1"


@pytest.mark.asyncio
async def test_get_site_to_site_vpn_not_found() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "net1", "purpose": "corporate"}]}

    with patch.object(vpn_module, "get_network_client", return_value=client):
        with pytest.raises(ResourceNotFoundError):
            await get_site_to_site_vpn("default", "vpn-missing")


@pytest.mark.asyncio
async def test_update_site_to_site_vpn_dry_run() -> None:
    client = _make_client()
    client.get.return_value = {"_id": "vpn1", "name": "Old", "purpose": "site-vpn", "enabled": True}

    with patch.object(vpn_module, "get_network_client", return_value=client):
        result = await update_site_to_site_vpn(
            "default", "vpn1", name="New", enabled=False, confirm=True, dry_run=True
        )

    assert result["dry_run"] is True
    assert result["updates"]["name"] == "New"
    client.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_site_to_site_vpn_requires_confirm() -> None:
    with pytest.raises(ValidationError):
        await update_site_to_site_vpn("default", "vpn1", name="New", confirm=False)


@pytest.mark.asyncio
async def test_update_site_to_site_vpn_success() -> None:
    client = _make_client()
    client.get.return_value = {"_id": "vpn1", "name": "Old", "purpose": "site-vpn", "enabled": True}

    with patch.object(vpn_module, "get_network_client", return_value=client):
        result = await update_site_to_site_vpn("default", "vpn1", name="New", confirm=True)

    assert result["success"] is True
    payload = client.put.call_args.kwargs["json_data"]
    assert payload["name"] == "New"
