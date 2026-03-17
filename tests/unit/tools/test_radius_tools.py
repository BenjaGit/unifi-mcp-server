"""Unit tests for RADIUS and guest portal tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.radius as radius_module
from src.api.network_client import SiteInfo
from src.tools.radius import (
    configure_guest_portal,
    create_hotspot_package,
    create_radius_account,
    create_radius_profile,
    delete_hotspot_package,
    delete_radius_account,
    delete_radius_profile,
    get_guest_portal_config,
    get_hotspot_package,
    list_hotspot_packages,
    list_radius_accounts,
    list_radius_profiles,
    update_hotspot_package,
    update_radius_account,
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
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_radius_profiles_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "p1", "name": "Corp", "site_id": "default"}]}

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await list_radius_profiles("default")

    assert len(result) == 1
    assert result[0]["id"] == "p1"
    client.get.assert_called_once_with("/proxy/network/api/s/default/rest/radiusprofile")


@pytest.mark.asyncio
async def test_create_radius_profile_dry_run_redacts_secrets() -> None:
    client = _make_client()

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await create_radius_profile(
            site_id="default",
            name="Corp",
            auth_server="radius.example.com",
            auth_secret="secret",
            acct_server="acct.example.com",
            acct_secret="acct-secret",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["payload"]["auth_secret"] == "***REDACTED***"
    assert result["payload"]["acct_secret"] == "***REDACTED***"
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_delete_radius_profile_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await delete_radius_profile("default", "p1", confirm=False)


@pytest.mark.asyncio
async def test_list_radius_accounts_redacts_password() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [{"_id": "a1", "name": "alice", "x_password": "pw", "site_id": "default"}]
    }

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await list_radius_accounts("default")

    assert result[0]["password"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_create_radius_account_vlan_sets_tunnel_defaults() -> None:
    client = _make_client()
    client.post.return_value = {
        "data": {
            "_id": "a1",
            "name": "alice",
            "x_password": "pw",
            "site_id": "default",
            "vlan": 10,
            "tunnel_type": 13,
            "tunnel_medium_type": 6,
        }
    }

    with (
        patch.object(radius_module, "get_network_client", return_value=client),
        patch.object(radius_module, "audit_action", new=AsyncMock()),
    ):
        result = await create_radius_account(
            site_id="default",
            username="alice",
            password="pw",
            vlan_id=10,
            confirm=True,
        )

    payload = client.post.call_args.kwargs["json_data"]
    assert payload["vlan"] == 10
    assert payload["tunnel_type"] == 13
    assert payload["tunnel_medium_type"] == 6
    assert result["password"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_update_radius_account_requires_one_field() -> None:
    with pytest.raises(ValueError):
        await update_radius_account("default", "a1", confirm=True)


@pytest.mark.asyncio
async def test_delete_radius_account_dry_run() -> None:
    client = _make_client()

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await delete_radius_account("default", "a1", confirm=True, dry_run=True)

    assert result == {"dry_run": True, "account_id": "a1"}
    client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_get_guest_portal_config_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"key": "mgmt", "site_id": "default"},
            {
                "key": "guest_access",
                "site_id": "default",
                "enabled": True,
                "portal_title": "Guest WiFi",
                "auth_method": "voucher",
                "session_timeout": 480,
            },
        ]
    }

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await get_guest_portal_config("default")

    assert result["portal_title"] == "Guest WiFi"
    assert result["auth_method"] == "voucher"


@pytest.mark.asyncio
async def test_configure_guest_portal_dry_run_redacts_password() -> None:
    client = _make_client()

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await configure_guest_portal(
            site_id="default",
            auth_method="password",
            password="pw",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["payload"]["password"] == "***REDACTED***"
    client.put.assert_not_called()


@pytest.mark.asyncio
async def test_list_hotspot_packages_not_found_returns_empty() -> None:
    client = _make_client()
    client.get.side_effect = RuntimeError("404 not found")

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await list_hotspot_packages("default")

    assert result == []


@pytest.mark.asyncio
async def test_create_hotspot_package_success() -> None:
    client = _make_client()
    client.post.return_value = {
        "data": {
            "_id": "h1",
            "name": "1 hour",
            "duration_minutes": 60,
            "enabled": True,
            "site_id": "default",
        }
    }

    with (
        patch.object(radius_module, "get_network_client", return_value=client),
        patch.object(radius_module, "audit_action", new=AsyncMock()),
    ):
        result = await create_hotspot_package(
            site_id="default",
            name="1 hour",
            duration_minutes=60,
            confirm=True,
        )

    assert result["id"] == "h1"
    client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_hotspot_package_filters_by_id() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {
                "_id": "h1",
                "name": "First",
                "duration_minutes": 60,
                "enabled": True,
                "site_id": "default",
            },
            {
                "_id": "h2",
                "name": "Second",
                "duration_minutes": 120,
                "enabled": True,
                "site_id": "default",
            },
        ]
    }

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await get_hotspot_package("default", "h2")

    assert result["id"] == "h2"
    assert result["name"] == "Second"


@pytest.mark.asyncio
async def test_update_hotspot_package_dry_run() -> None:
    client = _make_client()

    with patch.object(radius_module, "get_network_client", return_value=client):
        result = await update_hotspot_package(
            site_id="default",
            package_id="h1",
            name="updated",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["payload"] == {"name": "updated"}
    client.put.assert_not_called()


@pytest.mark.asyncio
async def test_delete_hotspot_package_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await delete_hotspot_package("default", "h1", confirm=False)
