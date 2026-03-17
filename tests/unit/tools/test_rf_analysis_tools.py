"""Unit tests for RF analysis tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.rf_analysis as rf_module
from src.api.network_client import SiteInfo
from src.tools.rf_analysis import list_available_channels, list_rogue_aps
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    return client


SAMPLE_ROGUE_APS = [
    {
        "essid": "NeighborWifi",
        "bssid": "00:54:af:b4:6e:be",
        "channel": 11,
        "signal": -85,
        "security": "WPA2-Personal",
        "is_rogue": False,
        "age": 3600,
    },
    {
        "essid": "SuspiciousAP",
        "bssid": "aa:bb:cc:dd:ee:ff",
        "channel": 6,
        "signal": -70,
        "security": "OPEN",
        "is_rogue": True,
        "age": 7200,
    },
    {
        "essid": "OldAP",
        "bssid": "11:22:33:44:55:66",
        "channel": 1,
        "signal": -90,
        "security": "WPA2-Personal",
        "is_rogue": False,
        "age": 90000,
    },
]


@pytest.mark.asyncio
async def test_list_rogue_aps_basic() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_ROGUE_APS[:2]}

    with patch.object(rf_module, "get_network_client", return_value=client):
        result = await list_rogue_aps("default")

    assert result["count"] == 2
    assert result["rogue_count"] == 1


@pytest.mark.asyncio
async def test_list_rogue_aps_within_filter() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_ROGUE_APS}

    with patch.object(rf_module, "get_network_client", return_value=client):
        result = await list_rogue_aps("default", within=1)

    assert result["count"] == 1
    assert result["aps"][0]["essid"] == "NeighborWifi"


@pytest.mark.asyncio
async def test_list_rogue_aps_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(rf_module, "get_network_client", return_value=client):
        await list_rogue_aps("default")

    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_rogue_aps_invalid_site_id() -> None:
    with pytest.raises((ValidationError, Exception)):
        await list_rogue_aps("")


@pytest.mark.asyncio
async def test_list_available_channels_basic() -> None:
    client = _make_client()
    mock_channels = [
        {"channel": 1, "freq": 2412, "band": "2g"},
        {"channel": 36, "freq": 5180, "band": "5g"},
    ]
    client.get.return_value = {"data": mock_channels}

    with patch.object(rf_module, "get_network_client", return_value=client):
        result = await list_available_channels("default")

    assert result["count"] == 2
    client.get.assert_awaited_once_with("/proxy/network/api/s/default/stat/current-channel")
