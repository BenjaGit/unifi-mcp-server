"""Unit tests for device control tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.network_client import SiteInfo
from src.tools.device_control import (
    cancel_device_migration,
    delete_device,
    force_provision_device,
    get_speedtest_status,
    locate_device,
    migrate_device,
    restart_device,
    run_speedtest,
    trigger_spectrum_scan,
    upgrade_device,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError

# =============================================================================
# restart_device Tests
# =============================================================================


@pytest.mark.asyncio
async def test_restart_device_success():
    """Test successful device restart."""
    mock_devices_response = {
        "data": [
            {
                "id": "device1",
                "macAddress": "00:11:22:33:44:55",
                "name": "Test AP",
                "model": "UAP-AC-PRO",
            }
        ]
    }
    mock_restart_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_restart_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await restart_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"
    assert result["message"] == "Device restart initiated"
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_restart_device_dry_run():
    """Test device restart dry run."""
    result = await restart_device(
        site_id="default",
        device_mac="00:11:22:33:44:55",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_restart"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_restart_device_no_confirm():
    """Test device restart fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await restart_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_restart_device_not_found():
    """Test restart of non-existent device."""
    mock_devices_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await restart_device(
                site_id="default",
                device_mac="aa:bb:cc:dd:ee:ff",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_restart_device_invalid_mac():
    """Test device restart with invalid MAC address."""
    with pytest.raises(ValidationError) as excinfo:
        await restart_device(
            site_id="default",
            device_mac="invalid-mac",
            confirm=True,
        )

    assert "mac" in str(excinfo.value).lower() or "invalid" in str(excinfo.value).lower()


# =============================================================================
# locate_device Tests
# =============================================================================


@pytest.mark.asyncio
async def test_locate_device_enable():
    """Test enabling device locate mode."""
    mock_locate_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.post = AsyncMock(return_value=mock_locate_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await locate_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            enabled=True,
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"
    assert result["locate_enabled"] is True
    assert result["message"] == "Locate mode enabled"

    # Verify legacy cmd/devmgr was used (locate not in Integration API)
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["cmd"] == "set-locate"
    assert json_data["mac"] == "00:11:22:33:44:55"
    assert "cmd/devmgr" in call_args[0][0]


@pytest.mark.asyncio
async def test_locate_device_disable():
    """Test disabling device locate mode."""
    mock_locate_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.post = AsyncMock(return_value=mock_locate_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await locate_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            enabled=False,
            confirm=True,
        )

    assert result["success"] is True
    assert result["locate_enabled"] is False
    assert result["message"] == "Locate mode disabled"

    # Verify legacy cmd/devmgr was used
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["cmd"] == "unset-locate"


@pytest.mark.asyncio
async def test_locate_device_dry_run():
    """Test device locate mode dry run."""
    result = await locate_device(
        site_id="default",
        device_mac="00:11:22:33:44:55",
        enabled=True,
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_enable"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_locate_device_disable_dry_run():
    """Test device locate mode disable dry run."""
    result = await locate_device(
        site_id="default",
        device_mac="00:11:22:33:44:55",
        enabled=False,
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_disable"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_locate_device_no_confirm():
    """Test device locate fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await locate_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            enabled=True,
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_locate_device_posts_to_legacy():
    """Test locate uses legacy cmd/devmgr endpoint."""
    mock_locate_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.post = AsyncMock(return_value=mock_locate_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await locate_device(
            site_id="default",
            device_mac="aa:bb:cc:dd:ee:ff",
            enabled=True,
            confirm=True,
        )

    assert result["success"] is True
    # Verify legacy path used, not integration path
    call_args = mock_client.post.call_args
    assert "cmd/devmgr" in call_args[0][0]
    mock_client.get.assert_not_called()


# =============================================================================
# upgrade_device Tests
# =============================================================================


@pytest.mark.asyncio
async def test_upgrade_device_latest():
    """Test triggering firmware upgrade to latest version."""
    mock_devices_response = {
        "data": [
            {
                "_id": "device1",
                "mac": "00:11:22:33:44:55",
                "name": "Test AP",
                "version": "6.5.28",
                "model": "UAP-AC-PRO",
            }
        ]
    }
    mock_upgrade_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_upgrade_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await upgrade_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"
    assert result["message"] == "Firmware upgrade initiated"
    assert result["current_version"] == "6.5.28"

    # Verify legacy cmd/devmgr format (upgrade not in Integration API)
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["cmd"] == "upgrade"
    assert json_data["mac"] == "00:11:22:33:44:55"
    assert "url" not in json_data
    assert "cmd/devmgr" in call_args[0][0]


@pytest.mark.asyncio
async def test_upgrade_device_specific_firmware():
    """Test triggering firmware upgrade with specific firmware URL."""
    mock_devices_response = {
        "data": [
            {
                "_id": "device1",
                "mac": "00:11:22:33:44:55",
                "name": "Test AP",
                "version": "6.5.28",
            }
        ]
    }
    mock_upgrade_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_upgrade_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    firmware_url = "https://fw-update.ubnt.com/firmware/UAP-AC-PRO/6.6.55.unf"

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await upgrade_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            firmware_url=firmware_url,
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"

    # Verify firmware_url was included in legacy cmd/devmgr
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["cmd"] == "upgrade"
    assert json_data["url"] == firmware_url


@pytest.mark.asyncio
async def test_upgrade_device_dry_run():
    """Test device upgrade dry run."""
    result = await upgrade_device(
        site_id="default",
        device_mac="00:11:22:33:44:55",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_upgrade"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_upgrade_device_no_confirm():
    """Test device upgrade fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await upgrade_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_upgrade_device_not_found():
    """Test upgrade of non-existent device."""
    mock_devices_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await upgrade_device(
                site_id="default",
                device_mac="aa:bb:cc:dd:ee:ff",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_upgrade_device_invalid_mac():
    """Test device upgrade with invalid MAC address."""
    with pytest.raises(ValidationError) as excinfo:
        await upgrade_device(
            site_id="default",
            device_mac="invalid-mac",
            confirm=True,
        )

    assert "mac" in str(excinfo.value).lower() or "invalid" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_upgrade_device_with_version_info():
    """Test upgrade returns current version info."""
    mock_devices_response = {
        "data": [
            {
                "_id": "device1",
                "mac": "00:11:22:33:44:55",
                "name": "Test Switch",
                "version": "6.2.14",
                "model": "USW-24-POE",
            }
        ]
    }
    mock_upgrade_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_upgrade_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await upgrade_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["current_version"] == "6.2.14"


# =============================================================================
# Edge Cases and Additional Tests
# =============================================================================


@pytest.mark.asyncio
async def test_restart_device_multiple_devices():
    """Test restart finds correct device among multiple."""
    mock_devices_response = {
        "data": [
            {"id": "device1", "macAddress": "00:11:22:33:44:55", "name": "AP 1"},
            {"id": "device2", "macAddress": "aa:bb:cc:dd:ee:ff", "name": "AP 2"},
            {"id": "device3", "macAddress": "11:22:33:44:55:66", "name": "Switch 1"},
        ]
    }
    mock_restart_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_restart_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await restart_device(
            site_id="default",
            device_mac="aa:bb:cc:dd:ee:ff",
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "aa:bb:cc:dd:ee:ff"


@pytest.mark.asyncio
async def test_locate_device_default_enabled():
    """Test locate device defaults to enabled."""
    mock_locate_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.post = AsyncMock(return_value=mock_locate_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        # Don't pass enabled param - should default to True
        result = await locate_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["locate_enabled"] is True


@pytest.mark.asyncio
async def test_restart_device_mac_normalization():
    """Test that MAC address is normalized during comparison."""
    # Device in API uses colons, input uses colons
    mock_devices_response = {
        "data": [{"id": "device1", "macAddress": "00:11:22:33:44:55", "name": "Test AP"}]
    }
    mock_restart_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_restart_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        # Input MAC with different format (uppercase)
        result = await restart_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_devices_response_list_format():
    """Test handling when devices response is a list (auto-unwrapped)."""
    # Client auto-unwraps data, so response might be a list directly
    mock_devices_response = [
        {"id": "device1", "macAddress": "00:11:22:33:44:55", "name": "Test AP"}
    ]
    mock_restart_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.post = AsyncMock(return_value=mock_restart_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await restart_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["success"] is True


# =============================================================================
# delete_device Tests
# =============================================================================


@pytest.mark.asyncio
async def test_delete_device_success():
    """Test successful device deletion."""
    mock_devices_response = {
        "data": [
            {
                "id": "device-uuid-1",
                "macAddress": "00:11:22:33:44:55",
                "name": "Test AP",
                "model": "UAP-AC-PRO",
            }
        ]
    }
    mock_delete_response = {}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.delete = AsyncMock(return_value=mock_delete_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await delete_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"
    assert result["device_name"] == "Test AP"
    assert "removed" in result["message"].lower()
    mock_client.delete.assert_called_once_with(
        "/integration/v1/sites/uuid-default/devices/device-uuid-1"
    )


@pytest.mark.asyncio
async def test_delete_device_dry_run():
    """Test device deletion dry run."""
    result = await delete_device(
        site_id="default",
        device_mac="00:11:22:33:44:55",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_delete"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_delete_device_no_confirm():
    """Test device deletion fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await delete_device(
            site_id="default",
            device_mac="00:11:22:33:44:55",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_delete_device_not_found():
    """Test deletion of non-existent device."""
    mock_devices_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await delete_device(
                site_id="default",
                device_mac="aa:bb:cc:dd:ee:ff",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_delete_device_invalid_mac():
    """Test device deletion with invalid MAC address."""
    with pytest.raises(ValidationError):
        await delete_device(
            site_id="default",
            device_mac="invalid-mac",
            confirm=True,
        )


@pytest.mark.asyncio
async def test_delete_device_calls_correct_endpoint():
    """Test that DELETE is called on the correct Integration API path."""
    mock_devices_response = {
        "data": [{"id": "abc-def-123", "macAddress": "aa:bb:cc:dd:ee:ff", "name": "Switch"}]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="site-uuid"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock(return_value=mock_devices_response)
    mock_client.delete = AsyncMock(return_value={})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await delete_device(
            site_id="default",
            device_mac="aa:bb:cc:dd:ee:ff",
            confirm=True,
        )

    mock_client.delete.assert_called_once_with(
        "/integration/v1/sites/site-uuid/devices/abc-def-123"
    )


@pytest.mark.asyncio
async def test_delete_device_invalid_site_id():
    """Test device deletion with empty site_id."""
    with pytest.raises(ValidationError):
        await delete_device(
            site_id="",
            device_mac="00:11:22:33:44:55",
            confirm=True,
        )


# =============================================================================
# force_provision_device Tests
# =============================================================================


def _make_mock_dc_client(site_name="default", uuid="uuid-default"):
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name=site_name, uuid=uuid))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )
    mock_client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_client.get = AsyncMock()
    mock_client.post = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_force_provision_device_success():
    """Test successful device force provision."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"meta": {"rc": "ok"}})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await force_provision_device("default", "00:11:22:33:44:55", confirm=True)

    assert result["success"] is True
    assert result["device_mac"] == "00:11:22:33:44:55"
    call_args = mock_client.post.call_args
    assert call_args[1]["json_data"]["cmd"] == "force-provision"
    assert call_args[1]["json_data"]["mac"] == "00:11:22:33:44:55"
    assert "cmd/devmgr" in call_args[0][0]


@pytest.mark.asyncio
async def test_force_provision_device_dry_run():
    """Test device force provision dry run."""
    result = await force_provision_device(
        "default", "00:11:22:33:44:55", confirm=True, dry_run=True
    )
    assert result["dry_run"] is True
    assert result["would_provision"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
async def test_force_provision_device_no_confirm():
    """Test device force provision fails without confirmation."""
    with pytest.raises(ValidationError):
        await force_provision_device("default", "00:11:22:33:44:55", confirm=False)


@pytest.mark.asyncio
async def test_force_provision_device_invalid_mac():
    """Test device force provision with invalid MAC address."""
    with pytest.raises(ValidationError):
        await force_provision_device("default", "not-a-mac", confirm=True)


@pytest.mark.asyncio
async def test_force_provision_device_invalid_site_id():
    """Test device force provision with empty site_id."""
    with pytest.raises(ValidationError):
        await force_provision_device("", "00:11:22:33:44:55", confirm=True)


@pytest.mark.asyncio
async def test_force_provision_device_correct_endpoint():
    """Test force provision uses legacy cmd/devmgr with force-provision cmd."""
    mock_client = _make_mock_dc_client(site_name="mysite")
    mock_client.post = AsyncMock(return_value={})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await force_provision_device("mysite", "aa:bb:cc:dd:ee:ff", confirm=True)

    call_args = mock_client.post.call_args
    assert call_args[0][0] == "/proxy/network/api/s/mysite/cmd/devmgr"
    assert call_args[1]["json_data"]["cmd"] == "force-provision"


# =============================================================================
# run_speedtest Tests
# =============================================================================


@pytest.mark.asyncio
async def test_run_speedtest_success():
    """Test successful speed test start."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"meta": {"rc": "ok"}})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await run_speedtest("default", confirm=True)

    assert result["success"] is True
    assert "Speed test started" in result["message"]
    assert "get_speedtest_status" in result["message"]


@pytest.mark.asyncio
async def test_run_speedtest_no_confirm():
    """Test speed test fails without confirmation."""
    with pytest.raises(ValidationError):
        await run_speedtest("default", confirm=False)


@pytest.mark.asyncio
async def test_run_speedtest_correct_endpoint():
    """Test speed test uses legacy cmd/devmgr with speedtest cmd."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await run_speedtest("default", confirm=True)

    call_args = mock_client.post.call_args
    assert "cmd/devmgr" in call_args[0][0]
    assert call_args[1]["json_data"]["cmd"] == "speedtest"


# =============================================================================
# get_speedtest_status Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_speedtest_status_success():
    """Test successful speed test status retrieval."""
    mock_response = {"xput_download": 950.5, "xput_upload": 48.3, "latency": 12}
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await get_speedtest_status("default")

    assert result["xput_download"] == 950.5
    assert result["xput_upload"] == 48.3


@pytest.mark.asyncio
async def test_get_speedtest_status_correct_endpoint():
    """Test speed test status uses legacy cmd/devmgr with speedtest-status cmd."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await get_speedtest_status("default")

    call_args = mock_client.post.call_args
    assert "cmd/devmgr" in call_args[0][0]
    assert call_args[1]["json_data"]["cmd"] == "speedtest-status"


# =============================================================================
# trigger_spectrum_scan Tests
# =============================================================================


@pytest.mark.asyncio
async def test_trigger_spectrum_scan_success():
    """Test successful spectrum scan trigger."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"meta": {"rc": "ok"}})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await trigger_spectrum_scan("default", "00:11:22:33:44:55", confirm=True)

    assert result["success"] is True
    assert result["ap_mac"] == "00:11:22:33:44:55"
    assert "Spectrum scan triggered" in result["message"]


@pytest.mark.asyncio
async def test_trigger_spectrum_scan_no_confirm():
    """Test spectrum scan fails without confirmation."""
    with pytest.raises(ValidationError):
        await trigger_spectrum_scan("default", "00:11:22:33:44:55", confirm=False)


@pytest.mark.asyncio
async def test_trigger_spectrum_scan_invalid_mac():
    """Test spectrum scan with invalid MAC address."""
    with pytest.raises(ValidationError):
        await trigger_spectrum_scan("default", "bad-mac", confirm=True)


@pytest.mark.asyncio
async def test_trigger_spectrum_scan_correct_endpoint():
    """Test spectrum scan uses legacy cmd/devmgr with spectrum-scan cmd."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await trigger_spectrum_scan("default", "aa:bb:cc:dd:ee:ff", confirm=True)

    call_args = mock_client.post.call_args
    assert "cmd/devmgr" in call_args[0][0]
    assert call_args[1]["json_data"]["cmd"] == "spectrum-scan"
    assert call_args[1]["json_data"]["mac"] == "aa:bb:cc:dd:ee:ff"


# =============================================================================
# migrate_device Tests
# =============================================================================


@pytest.mark.asyncio
async def test_migrate_device_basic():
    """Test basic device migration."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"success": True})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await migrate_device(
            "default",
            "aa:bb:cc:dd:ee:ff",
            "https://new-controller.example.com:8080/inform",
            confirm=True,
        )

    assert result is not None
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_migrate_device_correct_cmd():
    """Test that correct migrate cmd is sent with mac and inform_url."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"success": True})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await migrate_device(
            "default",
            "aa:bb:cc:dd:ee:ff",
            "https://new.example.com:8080/inform",
            confirm=True,
        )

    payload = mock_client.post.call_args[1]["json_data"]
    assert payload["cmd"] == "migrate"
    assert payload["mac"] == "aa:bb:cc:dd:ee:ff"
    assert payload["inform_url"] == "https://new.example.com:8080/inform"


@pytest.mark.asyncio
async def test_migrate_device_dry_run():
    """Test dry run skips API call."""
    mock_client = _make_mock_dc_client()

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await migrate_device(
            "default",
            "aa:bb:cc:dd:ee:ff",
            "https://new.example.com:8080/inform",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_device_no_confirm():
    """Test that missing confirm raises error."""
    with pytest.raises(ValidationError):
        await migrate_device(
            "default",
            "aa:bb:cc:dd:ee:ff",
            "https://new.example.com:8080/inform",
            confirm=False,
        )


# =============================================================================
# cancel_device_migration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_device_migration_basic():
    """Test basic migration cancellation."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"success": True})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await cancel_device_migration("default", "aa:bb:cc:dd:ee:ff", confirm=True)

    assert result is not None
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_device_migration_correct_cmd():
    """Test that correct cancel-migrate cmd is sent."""
    mock_client = _make_mock_dc_client()
    mock_client.post = AsyncMock(return_value={"success": True})

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        await cancel_device_migration("default", "aa:bb:cc:dd:ee:ff", confirm=True)

    payload = mock_client.post.call_args[1]["json_data"]
    assert payload["cmd"] == "cancel-migrate"
    assert payload["mac"] == "aa:bb:cc:dd:ee:ff"


@pytest.mark.asyncio
async def test_cancel_device_migration_dry_run():
    """Test dry run skips API call."""
    mock_client = _make_mock_dc_client()

    with patch("src.tools.device_control.get_network_client", return_value=mock_client):
        result = await cancel_device_migration(
            "default", "aa:bb:cc:dd:ee:ff", confirm=True, dry_run=True
        )

    assert result["dry_run"] is True
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_device_migration_no_confirm():
    """Test that missing confirm raises error."""
    with pytest.raises(ValidationError):
        await cancel_device_migration("default", "aa:bb:cc:dd:ee:ff", confirm=False)
