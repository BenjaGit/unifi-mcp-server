"""Unit tests for events and alarms tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.events as events_module
from src.api.network_client import SiteInfo
from src.tools.events import archive_all_alarms, list_alarms, list_events
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


SAMPLE_EVENTS = [
    {"key": "EVT_AP_Connected", "msg": "AP connected", "time": 1700000003, "subsystem": "wlan"},
    {
        "key": "EVT_AP_Disconnected",
        "msg": "AP disconnected",
        "time": 1700000002,
        "subsystem": "wlan",
    },
    {"key": "EVT_SW_Connected", "msg": "Switch connected", "time": 1700000001, "subsystem": "lan"},
]

SAMPLE_ALARMS = [
    {"key": "alarm_ap_offline", "msg": "AP offline", "time": 1700000002, "archived": False},
    {"key": "alarm_sw_offline", "msg": "Switch offline", "time": 1700000001, "archived": True},
]


@pytest.mark.asyncio
async def test_list_events_basic() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_EVENTS}

    with patch.object(events_module, "get_network_client", return_value=client):
        result = await list_events("default")

    assert result["count"] == 3
    assert result["site_id"] == "default"


@pytest.mark.asyncio
async def test_list_events_filtering() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_EVENTS}

    with patch.object(events_module, "get_network_client", return_value=client):
        result = await list_events("default", event_type="EVT_AP")

    assert result["count"] == 2
    assert all(e["key"].startswith("EVT_AP") for e in result["events"])


@pytest.mark.asyncio
async def test_list_alarms_archived_filter() -> None:
    client = _make_client()
    client.get.return_value = {"data": SAMPLE_ALARMS}

    with patch.object(events_module, "get_network_client", return_value=client):
        result = await list_alarms("default", archived=True)

    assert result["count"] == 1
    assert result["alarms"][0]["archived"] is True


@pytest.mark.asyncio
async def test_archive_all_alarms_success() -> None:
    client = _make_client()

    with (
        patch.object(events_module, "get_network_client", return_value=client),
        patch.object(events_module, "log_audit", new=AsyncMock()),
    ):
        result = await archive_all_alarms("default", confirm=True)

    assert result["success"] is True
    client.post.assert_awaited_once_with(
        "/proxy/network/api/s/default/cmd/evtmgt",
        json_data={"cmd": "archive-all-alarms"},
    )


@pytest.mark.asyncio
async def test_archive_all_alarms_dry_run() -> None:
    client = _make_client()

    with (
        patch.object(events_module, "get_network_client", return_value=client),
        patch.object(events_module, "log_audit", new=AsyncMock()),
    ):
        result = await archive_all_alarms("default", confirm=True, dry_run=True)

    assert result["dry_run"] is True
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_archive_all_alarms_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await archive_all_alarms("default", confirm=False)
