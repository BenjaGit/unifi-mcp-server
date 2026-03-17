"""Unit tests for client management tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.clients as clients_module
from src.api.network_client import SiteInfo
from src.tools.clients import (
    get_client_details,
    get_client_statistics,
    list_active_clients,
    search_clients,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock(return_value={"data": []})
    return client


def _client_data(mac: str = "00:11:22:33:44:55", **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "mac": mac,
        "ip": "192.168.2.100",
        "hostname": "test-client",
        "name": "test-client",
        "is_wired": False,
        "tx_bytes": 1000000,
        "rx_bytes": 2000000,
        "tx_packets": 1000,
        "rx_packets": 2000,
        "tx_rate": 100000,
        "rx_rate": 200000,
        "signal": -65,
        "rssi": 35,
        "noise": -95,
        "uptime": 3600,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_get_client_details_from_active_clients() -> None:
    mac = "00:11:22:33:44:55"
    client = _make_client()
    client.get = AsyncMock(side_effect=[{"data": [_client_data(mac=mac)]}])

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await get_client_details("site-1", mac)

    assert result["mac"] == mac


@pytest.mark.asyncio
async def test_get_client_details_falls_back_to_all_users() -> None:
    mac = "aa:bb:cc:dd:ee:ff"
    client = _make_client()
    client.get = AsyncMock(side_effect=[{"data": []}, {"data": [_client_data(mac=mac)]}])

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await get_client_details("site-1", mac)

    assert result["mac"] == mac


@pytest.mark.asyncio
async def test_get_client_details_not_found() -> None:
    client = _make_client()
    client.get = AsyncMock(side_effect=[{"data": []}, {"data": []}])

    with patch.object(clients_module, "get_network_client", return_value=client):
        with pytest.raises(ResourceNotFoundError):
            await get_client_details("site-1", "ff:ff:ff:ff:ff:ff")


@pytest.mark.asyncio
async def test_get_client_statistics_success() -> None:
    mac = "00:11:22:33:44:55"
    client = _make_client()
    client.get = AsyncMock(side_effect=[{"data": [_client_data(mac=mac)]}])

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await get_client_statistics("site-1", mac)

    assert result["mac"] == mac
    assert result["tx_bytes"] == 1000000


@pytest.mark.asyncio
async def test_list_active_clients_success() -> None:
    client = _make_client()
    client.get = AsyncMock(
        side_effect=[{"data": [_client_data(), _client_data(mac="aa:bb:cc:dd:ee:ff")]}]
    )

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await list_active_clients("site-1")

    assert len(result) == 2


@pytest.mark.asyncio
async def test_search_clients_matches_hostname() -> None:
    client = _make_client()
    client.get = AsyncMock(
        side_effect=[
            {"data": [_client_data(mac="00:11:22:33:44:55", hostname="office-laptop")]},
            {"data": [_client_data(mac="aa:bb:cc:dd:ee:ff", hostname="home-phone")]},
        ]
    )

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await search_clients("site-1", "office")

    assert len(result) == 1
    assert result[0]["hostname"] == "office-laptop"


@pytest.mark.asyncio
async def test_search_clients_active_data_takes_priority() -> None:
    mac = "00:11:22:33:44:55"
    client = _make_client()
    client.get = AsyncMock(
        side_effect=[
            {"data": [_client_data(mac=mac, ip="192.168.2.100", hostname="current-hostname")]},
            {"data": [_client_data(mac=mac, ip="192.168.2.50", hostname="old-hostname")]},
        ]
    )

    with patch.object(clients_module, "get_network_client", return_value=client):
        result = await search_clients("site-1", "192.168.2.100")

    assert len(result) == 1
    assert result[0]["ip"] == "192.168.2.100"


@pytest.mark.asyncio
async def test_client_tools_validate_inputs() -> None:
    with pytest.raises(ValidationError):
        await get_client_details("", "00:11:22:33:44:55")
    with pytest.raises(ValidationError):
        await get_client_details("site-1", "invalid-mac")
