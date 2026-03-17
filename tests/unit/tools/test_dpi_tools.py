"""Unit tests for DPI tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.dpi as dpi_module
import src.tools.dpi_tools as dpi_tools_module
from src.api.network_client import SiteInfo
from src.tools.dpi import get_client_dpi, get_dpi_statistics, list_top_applications
from src.tools.dpi_tools import list_countries, list_dpi_applications, list_dpi_categories


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
async def test_get_dpi_statistics_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"app": "YouTube", "cat": "Streaming", "tx_bytes": 100, "rx_bytes": 300},
            {"app": "Netflix", "cat": "Streaming", "tx_bytes": 50, "rx_bytes": 150},
        ]
    }

    with patch.object(dpi_module, "get_network_client", return_value=client):
        result = await get_dpi_statistics("default")

    assert result["site_id"] == "default"
    assert result["total_applications"] == 2
    assert result["total_categories"] == 1


@pytest.mark.asyncio
async def test_get_dpi_statistics_invalid_time_range() -> None:
    with pytest.raises(ValueError):
        await get_dpi_statistics("default", time_range="invalid")


@pytest.mark.asyncio
async def test_list_top_applications_limit() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"app": f"App{i}", "cat": "Misc", "tx_bytes": i * 10, "rx_bytes": i * 30}
            for i in range(20)
        ]
    }

    with patch.object(dpi_module, "get_network_client", return_value=client):
        result = await list_top_applications("default", limit=5)

    assert len(result) == 5


@pytest.mark.asyncio
async def test_get_client_dpi_pagination() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"app": f"App{i}", "cat": "Misc", "tx_bytes": i * 10, "rx_bytes": i * 10}
            for i in range(10)
        ]
    }

    with patch.object(dpi_module, "get_network_client", return_value=client):
        result = await get_client_dpi("default", "aa:bb:cc:dd:ee:ff", limit=3, offset=2)

    assert len(result["applications"]) == 3
    assert result["total_applications"] == 10


@pytest.mark.asyncio
async def test_get_client_dpi_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(dpi_module, "get_network_client", return_value=client):
        await get_client_dpi("default", "aa:bb:cc:dd:ee:ff")

    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_dpi_categories_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"id": 1, "name": "Streaming"}]}

    with patch.object(dpi_tools_module, "get_network_client", return_value=client):
        result = await list_dpi_categories()

    assert len(result) == 1
    assert result[0]["name"] == "Streaming"


@pytest.mark.asyncio
async def test_list_dpi_applications_with_params() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"id": 1, "name": "YouTube", "cat": 1}]}

    with patch.object(dpi_tools_module, "get_network_client", return_value=client):
        await list_dpi_applications(limit=10, offset=5, filter_expr="name==YouTube")

    args, kwargs = client.get.call_args
    assert args[0] == "/integration/v1/dpi/applications"
    assert kwargs["params"]["limit"] == 10
    assert kwargs["params"]["offset"] == 5
    assert kwargs["params"]["filter"] == "name==YouTube"


@pytest.mark.asyncio
async def test_list_countries_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"code": "US", "name": "United States"}]}

    with patch.object(dpi_tools_module, "get_network_client", return_value=client):
        result = await list_countries()

    assert len(result) == 1
    assert result[0]["code"] == "US"
