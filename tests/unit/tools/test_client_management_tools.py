"""Unit tests for client management tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.client_management as cm_module
from src.api.network_client import SiteInfo
from src.tools.client_management import (
    authorize_guest,
    block_client,
    forget_client,
    limit_bandwidth,
    list_known_clients,
    reconnect_client,
    unauthorize_guest,
    unblock_client,
)
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.integration_path = MagicMock(
        side_effect=lambda site_uuid, ep: f"/integration/v1/sites/{site_uuid}/{ep}"
    )
    client.post = AsyncMock(return_value={"meta": {"rc": "ok"}})
    client.get = AsyncMock(return_value={"data": []})
    return client


@pytest.mark.asyncio
async def test_block_unblock_reconnect_success() -> None:
    client = _make_client()

    with (
        patch.object(cm_module, "get_network_client", return_value=client),
        patch.object(cm_module, "log_audit", new=AsyncMock()),
    ):
        blocked = await block_client("default", "00:11:22:33:44:55", confirm=True)
        unblocked = await unblock_client("default", "00:11:22:33:44:55", confirm=True)
        reconnected = await reconnect_client("default", "00:11:22:33:44:55", confirm=True)

    assert blocked["success"] is True
    assert unblocked["success"] is True
    assert reconnected["success"] is True


@pytest.mark.asyncio
async def test_authorize_guest_with_limits_success() -> None:
    client = _make_client()

    with (
        patch.object(cm_module, "get_network_client", return_value=client),
        patch.object(cm_module, "log_audit", new=AsyncMock()),
    ):
        result = await authorize_guest(
            site_id="default",
            client_mac="00:11:22:33:44:55",
            duration=7200,
            upload_limit_kbps=1024,
            download_limit_kbps=2048,
            confirm=True,
        )

    assert result["success"] is True
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["action"] == "authorize-guest"
    assert payload["params"]["uploadLimit"] == 1024


@pytest.mark.asyncio
async def test_limit_bandwidth_success() -> None:
    client = _make_client()

    with (
        patch.object(cm_module, "get_network_client", return_value=client),
        patch.object(cm_module, "log_audit", new=AsyncMock()),
    ):
        result = await limit_bandwidth(
            site_id="default",
            client_mac="00:11:22:33:44:55",
            download_limit_kbps=5000,
            confirm=True,
        )

    assert result["success"] is True
    payload = client.post.call_args.kwargs["json_data"]
    assert payload["action"] == "limit-bandwidth"
    assert payload["params"]["downloadLimit"] == 5000


@pytest.mark.asyncio
async def test_forget_client_and_unauthorize_guest_success() -> None:
    client = _make_client()

    with (
        patch.object(cm_module, "get_network_client", return_value=client),
        patch.object(cm_module, "log_audit", new=AsyncMock()),
    ):
        forgot = await forget_client("default", "00:11:22:33:44:55", confirm=True)
        unauth = await unauthorize_guest("default", "00:11:22:33:44:55", confirm=True)

    assert forgot["success"] is True
    assert unauth["success"] is True


@pytest.mark.asyncio
async def test_list_known_clients_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "c1", "mac": "00:11:22:33:44:55", "hostname": "laptop"},
            {"_id": "c2", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "phone"},
        ]
    }

    with patch.object(cm_module, "get_network_client", return_value=client):
        result = await list_known_clients("default", limit=1)

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_client_management_dry_runs() -> None:
    client = _make_client()

    with (
        patch.object(cm_module, "get_network_client", return_value=client),
        patch.object(cm_module, "log_audit", new=AsyncMock()),
    ):
        block_result = await block_client(
            "default", "00:11:22:33:44:55", confirm=True, dry_run=True
        )
        auth_result = await authorize_guest(
            "default", "00:11:22:33:44:55", duration=60, confirm=True, dry_run=True
        )

    assert block_result["dry_run"] is True
    assert auth_result["dry_run"] is True
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_client_management_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await block_client("default", "00:11:22:33:44:55", confirm=False)
    with pytest.raises(ValidationError):
        await reconnect_client("default", "00:11:22:33:44:55", confirm=False)
    with pytest.raises(ValidationError):
        await authorize_guest("default", "00:11:22:33:44:55", 60, confirm=False)


@pytest.mark.asyncio
async def test_limit_bandwidth_validates_positive_limits() -> None:
    with pytest.raises(ValueError):
        await limit_bandwidth("default", "00:11:22:33:44:55", upload_limit_kbps=0, confirm=True)
