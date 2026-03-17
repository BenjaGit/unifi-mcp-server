"""Unit tests for historical reports and sessions tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.reports as reports_module
from src.api.network_client import SiteInfo
from src.tools.reports import get_historical_report, list_sessions


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_historical_report_basic() -> None:
    client = _make_client()
    client.post.return_value = {"data": [{"time": 1700000000, "bytes": 1234567, "num_sta": 5}]}

    with patch.object(reports_module, "get_network_client", return_value=client):
        result = await get_historical_report(
            site_id="default",
            interval="hourly",
            report_type="site",
            start=1700000000,
            end=1700003600,
        )

    assert result["count"] == 1
    assert result["interval"] == "hourly"
    assert result["report_type"] == "site"


@pytest.mark.asyncio
async def test_get_historical_report_validates_inputs() -> None:
    with pytest.raises(ValueError, match="interval"):
        await get_historical_report(
            site_id="default",
            interval="weekly",
            report_type="site",
            start=1700000000,
            end=1700086400,
        )

    with pytest.raises(ValueError, match="report_type"):
        await get_historical_report(
            site_id="default",
            interval="hourly",
            report_type="gateway",
            start=1700000000,
            end=1700086400,
        )


@pytest.mark.asyncio
async def test_get_historical_report_custom_attrs() -> None:
    client = _make_client()
    client.post.return_value = {"data": []}

    with patch.object(reports_module, "get_network_client", return_value=client):
        await get_historical_report(
            site_id="default",
            interval="5minutes",
            report_type="user",
            start=1700000000,
            end=1700000300,
            attrs=["rx_bytes", "tx_bytes"],
        )

    payload = client.post.call_args.kwargs["json_data"]
    assert payload["attrs"] == ["rx_bytes", "tx_bytes"]


@pytest.mark.asyncio
async def test_list_sessions_basic() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"mac": "aa:bb:cc:dd:ee:ff", "hostname": "laptop", "duration": 3600},
            {"mac": "11:22:33:44:55:66", "hostname": "phone", "duration": 1800},
        ]
    }

    with patch.object(reports_module, "get_network_client", return_value=client):
        result = await list_sessions("default", limit=1)

    assert result["count"] == 1
    assert len(result["sessions"]) == 1


@pytest.mark.asyncio
async def test_list_sessions_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(reports_module, "get_network_client", return_value=client):
        await list_sessions("default")

    client.authenticate.assert_awaited_once()
