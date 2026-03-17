"""Unit tests for site administration tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.site_admin as site_admin_module
from src.api.network_client import SiteInfo
from src.tools.site_admin import create_site, delete_site, move_device
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.post = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_create_site_basic() -> None:
    client = _make_client()
    client.post.return_value = {"data": [{"name": "newsite"}]}

    with (
        patch.object(site_admin_module, "get_network_client", return_value=client),
        patch.object(site_admin_module, "log_audit", new=AsyncMock()),
    ):
        result = await create_site("default", "newsite", "New Site", confirm=True)

    assert result is not None
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "add-site"


@pytest.mark.asyncio
async def test_create_site_dry_run() -> None:
    client = _make_client()

    with (
        patch.object(site_admin_module, "get_network_client", return_value=client),
        patch.object(site_admin_module, "log_audit", new=AsyncMock()),
    ):
        result = await create_site("default", "testsite", "Test", confirm=True, dry_run=True)

    assert result["dry_run"] is True
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_delete_site_success() -> None:
    client = _make_client()

    with (
        patch.object(site_admin_module, "get_network_client", return_value=client),
        patch.object(site_admin_module, "log_audit", new=AsyncMock()),
    ):
        result = await delete_site("default", "oldsite", confirm=True)

    assert result["success"] is True
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "delete-site"


@pytest.mark.asyncio
async def test_move_device_success() -> None:
    client = _make_client()
    client.post.return_value = {"success": True}

    with (
        patch.object(site_admin_module, "get_network_client", return_value=client),
        patch.object(site_admin_module, "log_audit", new=AsyncMock()),
    ):
        result = await move_device("default", "aa:bb:cc:dd:ee:ff", "site2", confirm=True)

    assert result["success"] is True
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "move-device"


@pytest.mark.asyncio
async def test_site_admin_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await create_site("default", "testsite", "Test", confirm=False)
    with pytest.raises(ValidationError):
        await delete_site("default", "oldsite", confirm=False)
    with pytest.raises(ValidationError):
        await move_device("default", "aa:bb:cc:dd:ee:ff", "site2", confirm=False)
