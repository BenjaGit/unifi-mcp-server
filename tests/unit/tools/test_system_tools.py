"""Unit tests for system control tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.system as system_module
from src.api.network_client import SiteInfo
from src.tools.system import clear_dpi_counters, poweroff_gateway, reboot_gateway
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.post = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_reboot_gateway_success() -> None:
    client = _make_client()

    with (
        patch.object(system_module, "get_network_client", return_value=client),
        patch.object(system_module, "log_audit", new=AsyncMock()),
    ):
        result = await reboot_gateway("default", confirm=True)

    assert result == {"success": True, "action": "reboot"}
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "reboot"


@pytest.mark.asyncio
async def test_poweroff_gateway_success() -> None:
    client = _make_client()

    with (
        patch.object(system_module, "get_network_client", return_value=client),
        patch.object(system_module, "log_audit", new=AsyncMock()),
    ):
        result = await poweroff_gateway("default", confirm=True)

    assert result == {"success": True, "action": "poweroff"}
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "poweroff"


@pytest.mark.asyncio
async def test_clear_dpi_counters_success() -> None:
    client = _make_client()

    with (
        patch.object(system_module, "get_network_client", return_value=client),
        patch.object(system_module, "log_audit", new=AsyncMock()),
    ):
        result = await clear_dpi_counters("default", confirm=True)

    assert result == {"success": True, "action": "clear_dpi"}
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "clear-dpi"


@pytest.mark.asyncio
async def test_system_tools_dry_run() -> None:
    client = _make_client()

    with (
        patch.object(system_module, "get_network_client", return_value=client),
        patch.object(system_module, "log_audit", new=AsyncMock()),
    ):
        reboot_result = await reboot_gateway("default", confirm=True, dry_run=True)
        poweroff_result = await poweroff_gateway("default", confirm=True, dry_run=True)
        clear_result = await clear_dpi_counters("default", confirm=True, dry_run=True)

    assert reboot_result["dry_run"] is True
    assert poweroff_result["dry_run"] is True
    assert clear_result["dry_run"] is True
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_system_tools_require_confirmation() -> None:
    with pytest.raises(ValidationError):
        await reboot_gateway("default", confirm=False)
    with pytest.raises(ValidationError):
        await poweroff_gateway("default", confirm=False)
    with pytest.raises(ValidationError):
        await clear_dpi_counters("default", confirm=False)
