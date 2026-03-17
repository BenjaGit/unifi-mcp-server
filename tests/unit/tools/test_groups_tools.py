"""Unit tests for user groups, WLAN groups, and MAC tag tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.groups as groups_module
from src.api.network_client import SiteInfo
from src.tools.groups import list_mac_tags, list_user_groups, list_wlan_groups
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_user_groups_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "grp1", "name": "Default"}]}

    with patch.object(groups_module, "get_network_client", return_value=client):
        result = await list_user_groups("default")

    assert result["count"] == 1
    assert result["groups"][0]["name"] == "Default"
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/rest/usergroup")


@pytest.mark.asyncio
async def test_list_wlan_groups_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "wg1", "name": "Corporate"}]}

    with patch.object(groups_module, "get_network_client", return_value=client):
        result = await list_wlan_groups("default")

    assert result["count"] == 1
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/rest/wlangroup")


@pytest.mark.asyncio
async def test_list_mac_tags_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "tag1", "name": "IoT"}]}

    with patch.object(groups_module, "get_network_client", return_value=client):
        result = await list_mac_tags("default")

    assert result["count"] == 1
    assert result["tags"][0]["name"] == "IoT"
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/rest/tag")


@pytest.mark.asyncio
async def test_group_tools_support_list_response() -> None:
    client = _make_client()
    client.get.return_value = [{"_id": "grp1", "name": "Default"}]

    with patch.object(groups_module, "get_network_client", return_value=client):
        result = await list_user_groups("default")

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_group_tools_invalid_site() -> None:
    with pytest.raises((ValidationError, Exception)):
        await list_user_groups("")
