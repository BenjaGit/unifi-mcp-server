"""Unit tests for firewall rules tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.firewall as fw_module
from src.api.network_client import SiteInfo
from src.tools.firewall import (
    create_firewall_group,
    create_firewall_rule,
    delete_firewall_group,
    delete_firewall_rule,
    list_firewall_groups,
    list_firewall_rules,
    update_firewall_group,
    update_firewall_rule,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError

# =============================================================================
# list_firewall_rules Tests - Task 16.1
# =============================================================================


@pytest.mark.asyncio
async def test_list_firewall_rules_success():
    """Test successful listing of firewall rules."""
    mock_response = {
        "data": [
            {
                "_id": "rule1",
                "name": "Allow HTTP",
                "action": "accept",
                "enabled": True,
                "protocol": "tcp",
                "dst_port": 80,
            },
            {
                "_id": "rule2",
                "name": "Block Telnet",
                "action": "drop",
                "enabled": True,
                "protocol": "tcp",
                "dst_port": 23,
            },
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_rules(site_id="default")

    assert len(result) == 2
    assert result[0]["_id"] == "rule1"
    assert result[0]["name"] == "Allow HTTP"
    assert result[1]["_id"] == "rule2"
    assert result[1]["name"] == "Block Telnet"
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_list_firewall_rules_empty():
    """Test listing firewall rules when none exist."""
    mock_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_rules(site_id="default")

    assert len(result) == 0
    assert result == []


@pytest.mark.asyncio
async def test_list_firewall_rules_pagination():
    """Test listing firewall rules with pagination."""
    mock_response = {
        "data": [
            {"_id": "rule1", "name": "Rule 1"},
            {"_id": "rule2", "name": "Rule 2"},
            {"_id": "rule3", "name": "Rule 3"},
            {"_id": "rule4", "name": "Rule 4"},
            {"_id": "rule5", "name": "Rule 5"},
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_rules(site_id="default", limit=2, offset=1)

    assert len(result) == 2
    assert result[0]["_id"] == "rule2"
    assert result[1]["_id"] == "rule3"


@pytest.mark.asyncio
async def test_list_firewall_rules_list_response():
    """Test listing firewall rules when response is auto-unwrapped list."""
    # Client may auto-unwrap data, so response could be a list directly
    mock_response = [
        {"_id": "rule1", "name": "Allow SSH", "action": "accept"},
        {"_id": "rule2", "name": "Block ICMP", "action": "drop"},
    ]

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_rules(site_id="default")

    assert len(result) == 2
    assert result[0]["name"] == "Allow SSH"


# =============================================================================
# create_firewall_rule Tests - Task 16.2 (allow, block, dry_run)
# =============================================================================


@pytest.mark.asyncio
async def test_create_firewall_rule_allow():
    """Test creating an allow firewall rule."""
    mock_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Allow Web Traffic",
                "action": "accept",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Allow Web Traffic",
            action="accept",
            confirm=True,
        )

    assert result["_id"] == "rule123"
    assert result["name"] == "Allow Web Traffic"
    assert result["action"] == "accept"
    mock_client.post.assert_called_once()

    # Verify request data
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["name"] == "Allow Web Traffic"
    assert json_data["action"] == "accept"
    assert json_data["enabled"] is True


@pytest.mark.asyncio
async def test_create_firewall_rule_block():
    """Test creating a block (drop) firewall rule."""
    mock_response = {
        "data": [
            {
                "_id": "rule456",
                "name": "Block Malicious Traffic",
                "action": "drop",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Block Malicious Traffic",
            action="drop",
            confirm=True,
        )

    assert result["_id"] == "rule456"
    assert result["action"] == "drop"

    # Verify request data
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["action"] == "drop"


@pytest.mark.asyncio
async def test_create_firewall_rule_reject():
    """Test creating a reject firewall rule."""
    mock_response = {
        "data": [
            {
                "_id": "rule789",
                "name": "Reject Spam",
                "action": "reject",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Reject Spam",
            action="reject",
            confirm=True,
        )

    assert result["action"] == "reject"


@pytest.mark.asyncio
async def test_create_firewall_rule_dry_run():
    """Test create firewall rule dry run."""
    result = await create_firewall_rule(
        site_id="default",
        name="Test Rule",
        action="accept",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert "would_create" in result
    assert result["would_create"]["name"] == "Test Rule"
    assert result["would_create"]["action"] == "accept"
    assert result["would_create"]["enabled"] is True


# =============================================================================
# create_firewall_rule Tests - Task 16.3 (with_port, with_source, no_confirm)
# =============================================================================


@pytest.mark.asyncio
async def test_create_firewall_rule_with_port():
    """Test creating a firewall rule with port specification."""
    mock_response = {
        "data": [
            {
                "_id": "rule_port",
                "name": "Allow HTTPS",
                "action": "accept",
                "protocol": "tcp",
                "dst_port": 443,
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Allow HTTPS",
            action="accept",
            protocol="tcp",
            port=443,
            confirm=True,
        )

    assert result["_id"] == "rule_port"
    assert result["dst_port"] == 443
    assert result["protocol"] == "tcp"

    # Verify request data includes port and protocol
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["protocol"] == "tcp"
    assert json_data["dst_port"] == 443


@pytest.mark.asyncio
async def test_create_firewall_rule_with_source():
    """Test creating a firewall rule with source address."""
    mock_response = {
        "data": [
            {
                "_id": "rule_src",
                "name": "Allow from LAN",
                "action": "accept",
                "src_address": "192.168.1.0/24",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Allow from LAN",
            action="accept",
            src_address="192.168.1.0/24",
            confirm=True,
        )

    assert result["src_address"] == "192.168.1.0/24"

    # Verify request data includes source
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["src_address"] == "192.168.1.0/24"


@pytest.mark.asyncio
async def test_create_firewall_rule_with_destination():
    """Test creating a firewall rule with destination address."""
    mock_response = {
        "data": [
            {
                "_id": "rule_dst",
                "name": "Block to Server",
                "action": "drop",
                "dst_address": "10.0.0.100/32",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Block to Server",
            action="drop",
            dst_address="10.0.0.100/32",
            confirm=True,
        )

    assert result["dst_address"] == "10.0.0.100/32"

    # Verify request data includes destination
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["dst_address"] == "10.0.0.100/32"


@pytest.mark.asyncio
async def test_create_firewall_rule_no_confirm():
    """Test create firewall rule fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await create_firewall_rule(
            site_id="default",
            name="Test Rule",
            action="accept",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_firewall_rule_invalid_action():
    """Test create firewall rule with invalid action."""
    with pytest.raises(ValueError) as excinfo:
        await create_firewall_rule(
            site_id="default",
            name="Test Rule",
            action="invalid_action",
            confirm=True,
        )

    assert "invalid action" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_firewall_rule_invalid_protocol():
    """Test create firewall rule with invalid protocol."""
    with pytest.raises(ValueError) as excinfo:
        await create_firewall_rule(
            site_id="default",
            name="Test Rule",
            action="accept",
            protocol="invalid_protocol",
            confirm=True,
        )

    assert "invalid protocol" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_firewall_rule_disabled():
    """Test creating a disabled firewall rule."""
    mock_response = {
        "data": [
            {
                "_id": "rule_disabled",
                "name": "Disabled Rule",
                "action": "accept",
                "enabled": False,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Disabled Rule",
            action="accept",
            enabled=False,
            confirm=True,
        )

    assert result["enabled"] is False

    # Verify request data includes enabled=False
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["enabled"] is False


@pytest.mark.asyncio
async def test_create_firewall_rule_full_options():
    """Test creating a firewall rule with all options specified."""
    mock_response = {
        "data": [
            {
                "_id": "rule_full",
                "name": "Full Options Rule",
                "action": "accept",
                "src_address": "192.168.1.0/24",
                "dst_address": "10.0.0.0/8",
                "protocol": "tcp",
                "dst_port": 8080,
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Full Options Rule",
            action="accept",
            src_address="192.168.1.0/24",
            dst_address="10.0.0.0/8",
            protocol="tcp",
            port=8080,
            enabled=True,
            confirm=True,
        )

    assert result["_id"] == "rule_full"
    assert result["src_address"] == "192.168.1.0/24"
    assert result["dst_address"] == "10.0.0.0/8"
    assert result["protocol"] == "tcp"
    assert result["dst_port"] == 8080

    # Verify all fields in request data
    call_args = mock_client.post.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["src_address"] == "192.168.1.0/24"
    assert json_data["dst_address"] == "10.0.0.0/8"
    assert json_data["protocol"] == "tcp"
    assert json_data["dst_port"] == 8080


# =============================================================================
# update_firewall_rule Tests - Task 16.4
# =============================================================================


@pytest.mark.asyncio
async def test_update_firewall_rule_success():
    """Test successful firewall rule update."""
    mock_rules_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Old Name",
                "action": "accept",
                "enabled": True,
            }
        ]
    }
    mock_update_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "New Name",
                "action": "accept",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.put = AsyncMock(return_value=mock_update_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            name="New Name",
            confirm=True,
        )

    assert result["_id"] == "rule123"
    assert result["name"] == "New Name"
    mock_client.put.assert_called_once()


@pytest.mark.asyncio
async def test_update_firewall_rule_action():
    """Test updating firewall rule action."""
    mock_rules_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Test Rule",
                "action": "accept",
                "enabled": True,
            }
        ]
    }
    mock_update_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Test Rule",
                "action": "drop",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.put = AsyncMock(return_value=mock_update_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            action="drop",
            confirm=True,
        )

    assert result["action"] == "drop"

    # Verify update data
    call_args = mock_client.put.call_args
    json_data = call_args[1]["json_data"]
    assert json_data["action"] == "drop"


@pytest.mark.asyncio
async def test_update_firewall_rule_dry_run():
    """Test update firewall rule dry run."""
    result = await update_firewall_rule(
        site_id="default",
        rule_id="rule123",
        name="Updated Name",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert "would_update" in result
    assert result["would_update"]["rule_id"] == "rule123"
    assert result["would_update"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_firewall_rule_no_confirm():
    """Test update firewall rule fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            name="New Name",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_firewall_rule_not_found():
    """Test updating a non-existent firewall rule."""
    mock_rules_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await update_firewall_rule(
                site_id="default",
                rule_id="nonexistent",
                name="New Name",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_update_firewall_rule_invalid_action():
    """Test update firewall rule with invalid action."""
    with pytest.raises(ValueError) as excinfo:
        await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            action="invalid",
            confirm=True,
        )

    assert "invalid action" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_firewall_rule_invalid_protocol():
    """Test update firewall rule with invalid protocol."""
    with pytest.raises(ValueError) as excinfo:
        await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            protocol="invalid",
            confirm=True,
        )

    assert "invalid protocol" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_firewall_rule_multiple_fields():
    """Test updating multiple firewall rule fields at once."""
    mock_rules_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Old Name",
                "action": "accept",
                "enabled": True,
            }
        ]
    }
    mock_update_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "New Name",
                "action": "drop",
                "src_address": "192.168.1.0/24",
                "protocol": "udp",
                "dst_port": 53,
                "enabled": False,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.put = AsyncMock(return_value=mock_update_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            name="New Name",
            action="drop",
            src_address="192.168.1.0/24",
            protocol="udp",
            port=53,
            enabled=False,
            confirm=True,
        )

    assert result["name"] == "New Name"
    assert result["action"] == "drop"
    assert result["enabled"] is False


# =============================================================================
# delete_firewall_rule Tests - Task 16.4
# =============================================================================


@pytest.mark.asyncio
async def test_delete_firewall_rule_success():
    """Test successful firewall rule deletion."""
    mock_rules_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Delete Me",
                "action": "accept",
            }
        ]
    }
    mock_delete_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.delete = AsyncMock(return_value=mock_delete_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await delete_firewall_rule(
            site_id="default",
            rule_id="rule123",
            confirm=True,
        )

    assert result["success"] is True
    assert result["deleted_rule_id"] == "rule123"
    mock_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_firewall_rule_dry_run():
    """Test delete firewall rule dry run."""
    result = await delete_firewall_rule(
        site_id="default",
        rule_id="rule123",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_delete"] == "rule123"


@pytest.mark.asyncio
async def test_delete_firewall_rule_no_confirm():
    """Test delete firewall rule fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await delete_firewall_rule(
            site_id="default",
            rule_id="rule123",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_delete_firewall_rule_not_found():
    """Test deleting a non-existent firewall rule."""
    mock_rules_response = {"data": []}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await delete_firewall_rule(
                site_id="default",
                rule_id="nonexistent",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_delete_firewall_rule_multiple_rules():
    """Test deleting correct rule when multiple exist."""
    mock_rules_response = {
        "data": [
            {"_id": "rule1", "name": "Rule 1"},
            {"_id": "rule2", "name": "Rule 2"},
            {"_id": "rule3", "name": "Rule 3"},
        ]
    }
    mock_delete_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.delete = AsyncMock(return_value=mock_delete_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await delete_firewall_rule(
            site_id="default",
            rule_id="rule2",
            confirm=True,
        )

    assert result["success"] is True
    assert result["deleted_rule_id"] == "rule2"

    # Verify correct endpoint called
    call_args = mock_client.delete.call_args
    assert "rule2" in call_args[0][0]


# =============================================================================
# Edge Cases and Additional Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_firewall_rule_udp_protocol():
    """Test creating a firewall rule with UDP protocol."""
    mock_response = {
        "data": [
            {
                "_id": "rule_udp",
                "name": "DNS Rule",
                "action": "accept",
                "protocol": "udp",
                "dst_port": 53,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="DNS Rule",
            action="accept",
            protocol="udp",
            port=53,
            confirm=True,
        )

    assert result["protocol"] == "udp"


@pytest.mark.asyncio
async def test_create_firewall_rule_icmp_protocol():
    """Test creating a firewall rule with ICMP protocol."""
    mock_response = {
        "data": [
            {
                "_id": "rule_icmp",
                "name": "Allow Ping",
                "action": "accept",
                "protocol": "icmp",
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Allow Ping",
            action="accept",
            protocol="icmp",
            confirm=True,
        )

    assert result["protocol"] == "icmp"


@pytest.mark.asyncio
async def test_create_firewall_rule_all_protocol():
    """Test creating a firewall rule with all protocols."""
    mock_response = {
        "data": [
            {
                "_id": "rule_all",
                "name": "Block All",
                "action": "drop",
                "protocol": "all",
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Block All",
            action="drop",
            protocol="all",
            confirm=True,
        )

    assert result["protocol"] == "all"


@pytest.mark.asyncio
async def test_update_firewall_rule_list_response():
    """Test update when rules response is auto-unwrapped list."""
    # Client may auto-unwrap data
    mock_rules_response = [
        {
            "_id": "rule123",
            "name": "Test Rule",
            "action": "accept",
            "enabled": True,
        }
    ]
    mock_update_response = {
        "data": [
            {
                "_id": "rule123",
                "name": "Updated Rule",
                "action": "accept",
                "enabled": True,
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.put = AsyncMock(return_value=mock_update_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_rule(
            site_id="default",
            rule_id="rule123",
            name="Updated Rule",
            confirm=True,
        )

    assert result["name"] == "Updated Rule"


@pytest.mark.asyncio
async def test_delete_firewall_rule_list_response():
    """Test delete when rules response is auto-unwrapped list."""
    # Client may auto-unwrap data
    mock_rules_response = [
        {"_id": "rule123", "name": "Delete Me"},
    ]
    mock_delete_response = {"meta": {"rc": "ok"}}

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_rules_response)
    mock_client.delete = AsyncMock(return_value=mock_delete_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await delete_firewall_rule(
            site_id="default",
            rule_id="rule123",
            confirm=True,
        )

    assert result["success"] is True


# =============================================================================
# Additional Coverage Tests - networkconf_id branches, error paths
# =============================================================================


@pytest.mark.asyncio
async def test_create_firewall_rule_with_networkconf_ids():
    """Test creation with src_networkconf_id and dst_networkconf_id set."""
    created = {
        "data": [
            {
                "_id": "rule-new",
                "name": "Inter-VLAN Rule",
                "action": "accept",
                "src_networkconf_id": "net1",
                "dst_networkconf_id": "net2",
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=created)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_rule(
            site_id="default",
            name="Inter-VLAN Rule",
            action="accept",
            src_networkconf_id="net1",
            dst_networkconf_id="net2",
            confirm=True,
        )

    assert result["name"] == "Inter-VLAN Rule"
    call_args = mock_client.post.call_args
    payload = call_args[1]["json_data"]
    assert payload["src_networkconf_id"] == "net1"
    assert payload["dst_networkconf_id"] == "net2"


@pytest.mark.asyncio
async def test_create_firewall_rule_with_src_dst_address():
    """Test creation with src_address, dst_address, protocol, and port."""
    created = {
        "data": [
            {
                "_id": "rule-new",
                "name": "Address Rule",
                "action": "drop",
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(return_value=created)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await create_firewall_rule(
            site_id="default",
            name="Address Rule",
            action="drop",
            src_address="10.0.0.0/24",
            dst_address="192.168.1.0/24",
            protocol="tcp",
            port=443,
            confirm=True,
        )

    call_args = mock_client.post.call_args
    payload = call_args[1]["json_data"]
    assert payload["src_address"] == "10.0.0.0/24"
    assert payload["dst_address"] == "192.168.1.0/24"
    assert payload["protocol"] == "tcp"
    assert payload["dst_port"] == 443


@pytest.mark.asyncio
async def test_create_firewall_rule_error_handling():
    """Test create firewall rule error handling path."""
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.post = AsyncMock(side_effect=RuntimeError("API error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="API error"):
            await create_firewall_rule(
                site_id="default",
                name="Fail Rule",
                action="accept",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_update_firewall_rule_with_all_fields():
    """Test update with all optional fields (src/dst address, protocol, port, enabled)."""
    existing_rules = {
        "data": [{"_id": "rule1", "name": "Old", "action": "accept", "ruleset": "WAN_IN"}]
    }
    updated = {
        "data": [
            {
                "_id": "rule1",
                "name": "New Name",
                "action": "drop",
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(return_value=existing_rules)
    mock_client.put = AsyncMock(return_value=updated)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await update_firewall_rule(
            site_id="default",
            rule_id="rule1",
            name="New Name",
            action="drop",
            src_address="10.0.0.0/8",
            dst_address="172.16.0.0/12",
            protocol="udp",
            port=53,
            enabled=False,
            confirm=True,
        )

    put_data = mock_client.put.call_args[1]["json_data"]
    assert put_data["name"] == "New Name"
    assert put_data["action"] == "drop"
    assert put_data["src_address"] == "10.0.0.0/8"
    assert put_data["dst_address"] == "172.16.0.0/12"
    assert put_data["protocol"] == "udp"
    assert put_data["dst_port"] == 53
    assert put_data["enabled"] is False


@pytest.mark.asyncio
async def test_update_firewall_rule_error_handling():
    """Test update firewall rule error handling path."""
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RuntimeError("API error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="API error"):
            await update_firewall_rule(
                site_id="default",
                rule_id="rule1",
                name="Test",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_delete_firewall_rule_error_handling():
    """Test delete firewall rule error handling path."""
    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RuntimeError("API error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    mock_client.legacy_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}"
    )

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="API error"):
            await delete_firewall_rule(
                site_id="default",
                rule_id="rule1",
                confirm=True,
            )


def _make_mock_fg_client():
    client = MagicMock()
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


SAMPLE_GROUPS = [
    {
        "_id": "grp1",
        "name": "TrustedHosts",
        "group_type": "address-group",
        "group_members": ["192.168.1.0/24"],
    },
    {"_id": "grp2", "name": "WebPorts", "group_type": "port-group", "group_members": ["80", "443"]},
]


# =============================================================================
# list_firewall_groups Tests
# =============================================================================


@pytest.mark.asyncio
async def test_list_firewall_groups_basic():
    """Test basic firewall group listing."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": SAMPLE_GROUPS})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_groups("default")

    assert len(result) == 2
    assert result[0]["name"] == "TrustedHosts"


@pytest.mark.asyncio
async def test_list_firewall_groups_correct_path():
    """Test that the correct rest/firewallgroup path is used."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": []})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await list_firewall_groups("default")

    mock_client.legacy_path.assert_called_once_with("default", "rest/firewallgroup")


@pytest.mark.asyncio
async def test_list_firewall_groups_empty():
    """Test listing with no groups."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": []})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await list_firewall_groups("default")

    assert len(result) == 0


# =============================================================================
# create_firewall_group Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_firewall_group_basic():
    """Test basic firewall group creation."""
    mock_client = _make_mock_fg_client()
    mock_client.post = AsyncMock(return_value={"data": [{"_id": "new-grp", "name": "MyGroup"}]})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_group(
            site_id="default",
            name="MyGroup",
            group_type="address-group",
            group_members=["10.0.0.0/8"],
            confirm=True,
        )

    assert result is not None
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_create_firewall_group_dry_run():
    """Test dry run skips API call."""
    mock_client = _make_mock_fg_client()

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await create_firewall_group(
            site_id="default",
            name="MyGroup",
            group_type="address-group",
            group_members=[],
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_create_firewall_group_no_confirm():
    """Test that missing confirm raises error."""
    with pytest.raises(ValidationError):
        await create_firewall_group(
            site_id="default",
            name="MyGroup",
            group_type="address-group",
            group_members=[],
            confirm=False,
        )


@pytest.mark.asyncio
async def test_create_firewall_group_payload():
    """Test that the correct payload is sent."""
    mock_client = _make_mock_fg_client()
    mock_client.post = AsyncMock(return_value={"_id": "new-grp"})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await create_firewall_group(
            site_id="default",
            name="TestGroup",
            group_type="port-group",
            group_members=["80", "443"],
            confirm=True,
        )

    payload = mock_client.post.call_args[1]["json_data"]
    assert payload["name"] == "TestGroup"
    assert payload["group_type"] == "port-group"
    assert payload["group_members"] == ["80", "443"]


# =============================================================================
# update_firewall_group Tests
# =============================================================================


@pytest.mark.asyncio
async def test_update_firewall_group_basic():
    """Test basic firewall group update."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": SAMPLE_GROUPS})
    mock_client.put = AsyncMock(return_value={"_id": "grp1", "name": "Renamed"})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_group(
            site_id="default",
            group_id="grp1",
            name="Renamed",
            confirm=True,
        )

    assert result is not None
    mock_client.put.assert_called_once()


@pytest.mark.asyncio
async def test_update_firewall_group_dry_run():
    """Test dry run skips API call."""
    mock_client = _make_mock_fg_client()

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await update_firewall_group(
            site_id="default",
            group_id="grp1",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    mock_client.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_firewall_group_not_found():
    """Test that updating non-existent group raises ResourceNotFoundError."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": SAMPLE_GROUPS})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        with pytest.raises(ResourceNotFoundError):
            await update_firewall_group(
                site_id="default",
                group_id="nonexistent",
                name="NewName",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_update_firewall_group_members():
    """Test that members are updated correctly."""
    mock_client = _make_mock_fg_client()
    mock_client.get = AsyncMock(return_value={"data": SAMPLE_GROUPS})
    mock_client.put = AsyncMock(return_value={"_id": "grp1"})

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await update_firewall_group(
            site_id="default",
            group_id="grp1",
            group_members=["10.0.0.0/8", "172.16.0.0/12"],
            confirm=True,
        )

    payload = mock_client.put.call_args[1]["json_data"]
    assert payload["group_members"] == ["10.0.0.0/8", "172.16.0.0/12"]


# =============================================================================
# delete_firewall_group Tests
# =============================================================================


@pytest.mark.asyncio
async def test_delete_firewall_group_basic():
    """Test basic firewall group deletion."""
    mock_client = _make_mock_fg_client()
    mock_client.delete = AsyncMock(return_value=None)

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await delete_firewall_group(
            site_id="default",
            group_id="grp1",
            confirm=True,
        )

    assert result["success"] is True
    assert result["group_id"] == "grp1"


@pytest.mark.asyncio
async def test_delete_firewall_group_dry_run():
    """Test dry run skips deletion."""
    mock_client = _make_mock_fg_client()

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        result = await delete_firewall_group(
            site_id="default",
            group_id="grp1",
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    mock_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_firewall_group_no_confirm():
    """Test that missing confirm raises error."""
    with pytest.raises(ValidationError):
        await delete_firewall_group(
            site_id="default",
            group_id="grp1",
            confirm=False,
        )


@pytest.mark.asyncio
async def test_delete_firewall_group_correct_path():
    """Test that the correct path is used for deletion."""
    mock_client = _make_mock_fg_client()
    mock_client.delete = AsyncMock(return_value=None)

    with patch.object(fw_module, "get_network_client", return_value=mock_client):
        await delete_firewall_group(
            site_id="default",
            group_id="grp99",
            confirm=True,
        )

    mock_client.legacy_path.assert_called_with("default", "rest/firewallgroup/grp99")
