"""Unit tests for site settings tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.settings as settings_module
from src.api.network_client import SiteInfo
from src.tools.settings import get_site_settings, update_site_setting
from src.utils.exceptions import ValidationError


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.put = AsyncMock()
    return client


SAMPLE_SETTINGS = [
    {"_id": "set1", "key": "connectivity", "enabled": True},
    {"_id": "set2", "key": "ips", "enabled": False, "ips_mode": "ids"},
    {"_id": "set3", "key": "dpi", "enabled": True},
]


@pytest.mark.asyncio
async def test_get_site_settings_basic() -> None:
    client = _make_mock_client()
    client.get.return_value = {"data": SAMPLE_SETTINGS}

    with patch.object(settings_module, "get_network_client", return_value=client):
        result = await get_site_settings("default")

    assert result["count"] == 3
    assert result["site_id"] == "default"
    assert len(result["settings"]) == 3


@pytest.mark.asyncio
async def test_get_site_settings_key_filter() -> None:
    client = _make_mock_client()
    client.get.return_value = {"data": SAMPLE_SETTINGS}

    with patch.object(settings_module, "get_network_client", return_value=client):
        result = await get_site_settings("default", key="ips")

    assert result["count"] == 1
    assert result["settings"][0]["key"] == "ips"


@pytest.mark.asyncio
async def test_get_site_settings_correct_path() -> None:
    client = _make_mock_client()
    client.get.return_value = {"data": []}

    with patch.object(settings_module, "get_network_client", return_value=client):
        await get_site_settings("default")

    client.legacy_path.assert_called_once_with("default", "rest/setting")


@pytest.mark.asyncio
async def test_get_site_settings_invalid_site() -> None:
    with pytest.raises(ValidationError):
        await get_site_settings("")


@pytest.mark.asyncio
async def test_get_site_settings_key_not_found() -> None:
    client = _make_mock_client()
    client.get.return_value = {"data": SAMPLE_SETTINGS}

    with patch.object(settings_module, "get_network_client", return_value=client):
        result = await get_site_settings("default", key="nonexistent")

    assert result["count"] == 0
    assert result["settings"] == []


@pytest.mark.asyncio
async def test_update_site_setting_basic() -> None:
    client = _make_mock_client()
    client.put.return_value = {"data": [{"_id": "set1", "key": "connectivity"}]}
    setting_data = {"_id": "set1", "key": "connectivity", "enabled": False}

    with (
        patch.object(settings_module, "get_network_client", return_value=client),
        patch.object(settings_module, "log_audit", new=AsyncMock()),
    ):
        result = await update_site_setting(
            site_id="default",
            setting_key="connectivity",
            setting_id="set1",
            setting_data=setting_data,
            confirm=True,
        )

    assert result is not None
    client.put.assert_called_once()


@pytest.mark.asyncio
async def test_update_site_setting_correct_path() -> None:
    client = _make_mock_client()
    client.put.return_value = {"_id": "set2"}

    with (
        patch.object(settings_module, "get_network_client", return_value=client),
        patch.object(settings_module, "log_audit", new=AsyncMock()),
    ):
        await update_site_setting(
            site_id="default",
            setting_key="ips",
            setting_id="set2",
            setting_data={"_id": "set2", "key": "ips"},
            confirm=True,
        )

    client.legacy_path.assert_called_with("default", "rest/setting/ips/set2")


@pytest.mark.asyncio
async def test_update_site_setting_dry_run() -> None:
    client = _make_mock_client()

    with (
        patch.object(settings_module, "get_network_client", return_value=client),
        patch.object(settings_module, "log_audit", new=AsyncMock()),
    ):
        result = await update_site_setting(
            site_id="default",
            setting_key="ips",
            setting_id="set2",
            setting_data={},
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    client.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_site_setting_no_confirm() -> None:
    with pytest.raises(ValidationError):
        await update_site_setting(
            site_id="default",
            setting_key="ips",
            setting_id="set2",
            setting_data={},
            confirm=False,
        )


@pytest.mark.asyncio
async def test_update_site_setting_invalid_site() -> None:
    with pytest.raises(ValidationError):
        await update_site_setting(
            site_id="",
            setting_key="ips",
            setting_id="set2",
            setting_data={},
            confirm=True,
        )
