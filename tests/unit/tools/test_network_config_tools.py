"""Unit tests for network configuration tools (Integration API)."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.network_client import SiteInfo
from src.tools.network_config import (
    _build_network_payload,
    _parse_subnet,
    create_network,
    delete_network,
    update_network,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError

SITE_ID = "default"
SITE_UUID = "uuid-default"
NETWORK_ID = "net-uuid-1234"


def _mock_client() -> MagicMock:
    """Create a standard mock pooled NetworkClient."""
    mock_instance = MagicMock()
    mock_instance.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid=SITE_UUID))
    mock_instance.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    mock_instance.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    mock_instance.get = AsyncMock()
    mock_instance.post = AsyncMock()
    mock_instance.put = AsyncMock()
    mock_instance.delete = AsyncMock()
    return mock_instance


@contextmanager
def patch_client(mock_client: MagicMock):
    with patch("src.tools.network_config.get_network_client", return_value=mock_client):
        yield mock_client


# =============================================================================
# Helper function tests
# =============================================================================


class TestParseSubnet:
    def test_standard_cidr(self):
        host_ip, prefix = _parse_subnet("192.168.1.0/24")
        assert host_ip == "192.168.1.1"
        assert prefix == 24

    def test_slash_16(self):
        host_ip, prefix = _parse_subnet("10.0.0.0/16")
        assert host_ip == "10.0.0.1"
        assert prefix == 16

    def test_non_zero_host_bits(self):
        # strict=False allows non-zero host bits
        host_ip, prefix = _parse_subnet("192.168.1.100/24")
        assert host_ip == "192.168.1.1"
        assert prefix == 24

    def test_invalid_subnet(self):
        with pytest.raises(ValidationError):
            _parse_subnet("not-a-subnet/24")


class TestBuildNetworkPayload:
    def test_full_create_payload(self):
        payload = _build_network_payload(
            name="TestNet",
            vlan_id=100,
            subnet="192.168.100.0/24",
            purpose="corporate",
            dhcp_enabled=True,
            dhcp_start="192.168.100.10",
            dhcp_stop="192.168.100.200",
            dhcp_dns_1="8.8.8.8",
            dhcp_dns_2="8.8.4.4",
            domain_name="test.local",
        )
        assert payload["name"] == "TestNet"
        assert payload["vlanId"] == 100
        assert payload["purpose"] == "CORPORATE"

        ipv4 = payload["ipv4Configuration"]
        assert ipv4["hostIpAddress"] == "192.168.100.1"
        assert ipv4["prefixLength"] == 24

        dhcp = ipv4["dhcpConfiguration"]
        assert dhcp["mode"] == "SERVER"
        assert dhcp["ipAddressRange"]["start"] == "192.168.100.10"
        assert dhcp["ipAddressRange"]["stop"] == "192.168.100.200"
        assert dhcp["dnsServerIpAddressesOverride"] == ["8.8.8.8", "8.8.4.4"]
        assert dhcp["domainName"] == "test.local"

    def test_partial_update_payload(self):
        payload = _build_network_payload(name="NewName")
        assert payload == {"name": "NewName"}
        assert "ipv4Configuration" not in payload

    def test_dhcp_disabled(self):
        payload = _build_network_payload(dhcp_enabled=False)
        dhcp = payload["ipv4Configuration"]["dhcpConfiguration"]
        assert dhcp["mode"] == "NONE"

    def test_purpose_with_hyphen(self):
        payload = _build_network_payload(purpose="vlan-only")
        assert payload["purpose"] == "VLAN_ONLY"

    def test_empty_payload(self):
        payload = _build_network_payload()
        assert payload == {}

    def test_dns_list_filters_none(self):
        """Only non-None DNS servers should appear in the list."""
        payload = _build_network_payload(dhcp_dns_1="8.8.8.8", dhcp_dns_3="1.1.1.1")
        dns = payload["ipv4Configuration"]["dhcpConfiguration"]["dnsServerIpAddressesOverride"]
        assert dns == ["8.8.8.8", "1.1.1.1"]


# =============================================================================
# create_network Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_network_corporate():
    """Test creating a corporate network via Integration API."""
    api_response = {
        "id": NETWORK_ID,
        "name": "Corporate LAN",
        "purpose": "CORPORATE",
        "vlanId": 10,
    }

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        result = await create_network(
            site_id=SITE_ID,
            name="Corporate LAN",
            vlan_id=10,
            subnet="192.168.10.0/24",
            purpose="corporate",
            confirm=True,
        )

    assert result["id"] == NETWORK_ID
    assert result["name"] == "Corporate LAN"
    mock_client.post.assert_called_once()

    # Verify Integration API path
    call_args = mock_client.post.call_args
    assert call_args[0][0] == f"/integration/v1/sites/{SITE_UUID}/networks"

    # Verify Integration API field names in payload
    json_data = call_args[1]["json_data"]
    assert json_data["name"] == "Corporate LAN"
    assert json_data["purpose"] == "CORPORATE"
    assert json_data["vlanId"] == 10
    assert json_data["ipv4Configuration"]["hostIpAddress"] == "192.168.10.1"
    assert json_data["ipv4Configuration"]["prefixLength"] == 24


@pytest.mark.asyncio
async def test_create_network_guest():
    """Test creating a guest network via Integration API."""
    api_response = {
        "id": "net-guest-uuid",
        "name": "Guest WiFi",
        "purpose": "GUEST",
        "vlanId": 100,
    }

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        result = await create_network(
            site_id=SITE_ID,
            name="Guest WiFi",
            vlan_id=100,
            subnet="10.0.100.0/24",
            purpose="guest",
            confirm=True,
        )

    assert result["name"] == "Guest WiFi"
    assert result["purpose"] == "GUEST"

    json_data = mock_client.post.call_args[1]["json_data"]
    assert json_data["purpose"] == "GUEST"


@pytest.mark.asyncio
async def test_create_network_dry_run():
    """Test create network dry run returns Integration API format."""
    result = await create_network(
        site_id=SITE_ID,
        name="Test Network",
        vlan_id=20,
        subnet="192.168.20.0/24",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert "would_create" in result
    # Dry run payload should use Integration API format
    payload = result["would_create"]
    assert payload["name"] == "Test Network"
    assert payload["vlanId"] == 20
    assert payload["ipv4Configuration"]["hostIpAddress"] == "192.168.20.1"


@pytest.mark.asyncio
async def test_create_network_no_confirm():
    """Test create network fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await create_network(
            site_id=SITE_ID,
            name="Test Network",
            vlan_id=10,
            subnet="192.168.10.0/24",
            confirm=False,
        )

    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_network_invalid_vlan_too_low():
    """Test create network with invalid VLAN ID (too low)."""
    with pytest.raises(ValidationError) as excinfo:
        await create_network(
            site_id=SITE_ID,
            name="Test Network",
            vlan_id=0,
            subnet="192.168.10.0/24",
            confirm=True,
        )
    assert "vlan" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_network_invalid_vlan_too_high():
    """Test create network with invalid VLAN ID (too high)."""
    with pytest.raises(ValidationError) as excinfo:
        await create_network(
            site_id=SITE_ID,
            name="Test Network",
            vlan_id=4095,
            subnet="192.168.10.0/24",
            confirm=True,
        )
    assert "vlan" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_network_invalid_purpose():
    """Test create network with invalid purpose."""
    with pytest.raises(ValidationError) as excinfo:
        await create_network(
            site_id=SITE_ID,
            name="Test Network",
            vlan_id=10,
            subnet="192.168.10.0/24",
            purpose="invalid_purpose",
            confirm=True,
        )
    assert "purpose" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_network_invalid_subnet():
    """Test create network with invalid subnet format."""
    with pytest.raises(ValidationError) as excinfo:
        await create_network(
            site_id=SITE_ID,
            name="Test Network",
            vlan_id=10,
            subnet="192.168.10.0",  # Missing CIDR notation
            confirm=True,
        )
    assert "subnet" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_network_with_dhcp():
    """Test creating a network with DHCP enabled and range specified."""
    api_response = {"id": NETWORK_ID, "name": "DHCP Network"}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        await create_network(
            site_id=SITE_ID,
            name="DHCP Network",
            vlan_id=30,
            subnet="192.168.30.0/24",
            dhcp_enabled=True,
            dhcp_start="192.168.30.100",
            dhcp_stop="192.168.30.200",
            confirm=True,
        )

    json_data = mock_client.post.call_args[1]["json_data"]
    dhcp = json_data["ipv4Configuration"]["dhcpConfiguration"]
    assert dhcp["mode"] == "SERVER"
    assert dhcp["ipAddressRange"]["start"] == "192.168.30.100"
    assert dhcp["ipAddressRange"]["stop"] == "192.168.30.200"


@pytest.mark.asyncio
async def test_create_network_no_dhcp():
    """Test creating a network with DHCP disabled."""
    api_response = {"id": NETWORK_ID, "name": "Static Network"}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        await create_network(
            site_id=SITE_ID,
            name="Static Network",
            vlan_id=40,
            subnet="192.168.40.0/24",
            dhcp_enabled=False,
            confirm=True,
        )

    json_data = mock_client.post.call_args[1]["json_data"]
    dhcp = json_data["ipv4Configuration"]["dhcpConfiguration"]
    assert dhcp["mode"] == "NONE"


@pytest.mark.asyncio
async def test_create_network_custom_dns():
    """Test creating a network with custom DNS servers."""
    api_response = {"id": NETWORK_ID, "name": "DNS Network"}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        await create_network(
            site_id=SITE_ID,
            name="DNS Network",
            vlan_id=50,
            subnet="192.168.50.0/24",
            dhcp_enabled=True,
            dhcp_dns_1="8.8.8.8",
            dhcp_dns_2="8.8.4.4",
            confirm=True,
        )

    json_data = mock_client.post.call_args[1]["json_data"]
    dhcp = json_data["ipv4Configuration"]["dhcpConfiguration"]
    assert dhcp["dnsServerIpAddressesOverride"] == ["8.8.8.8", "8.8.4.4"]


@pytest.mark.asyncio
async def test_create_network_with_domain_name():
    """Test creating a network with domain name for DHCP."""
    api_response = {"id": NETWORK_ID, "name": "Domain Network"}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        await create_network(
            site_id=SITE_ID,
            name="Domain Network",
            vlan_id=60,
            subnet="192.168.60.0/24",
            dhcp_enabled=True,
            domain_name="example.local",
            confirm=True,
        )

    json_data = mock_client.post.call_args[1]["json_data"]
    dhcp = json_data["ipv4Configuration"]["dhcpConfiguration"]
    assert dhcp["domainName"] == "example.local"


@pytest.mark.asyncio
async def test_create_network_vlan_only_purpose():
    """Test creating a VLAN-only network."""
    api_response = {"id": NETWORK_ID, "name": "VLAN Only", "purpose": "VLAN_ONLY"}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        result = await create_network(
            site_id=SITE_ID,
            name="VLAN Only",
            vlan_id=200,
            subnet="192.168.200.0/24",
            purpose="vlan-only",
            confirm=True,
        )

    assert result["purpose"] == "VLAN_ONLY"
    json_data = mock_client.post.call_args[1]["json_data"]
    assert json_data["purpose"] == "VLAN_ONLY"


@pytest.mark.asyncio
async def test_create_network_boundary_vlan_min():
    """Test creating a network with minimum valid VLAN ID."""
    api_response = {"id": NETWORK_ID, "name": "Min VLAN", "vlanId": 1}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        result = await create_network(
            site_id=SITE_ID,
            name="Min VLAN",
            vlan_id=1,
            subnet="192.168.1.0/24",
            confirm=True,
        )

    assert result["vlanId"] == 1


@pytest.mark.asyncio
async def test_create_network_boundary_vlan_max():
    """Test creating a network with maximum valid VLAN ID."""
    api_response = {"id": NETWORK_ID, "name": "Max VLAN", "vlanId": 4094}

    mock_client = _mock_client()
    mock_client.post = AsyncMock(return_value=api_response)

    with patch_client(mock_client):
        result = await create_network(
            site_id=SITE_ID,
            name="Max VLAN",
            vlan_id=4094,
            subnet="10.94.0.0/24",
            confirm=True,
        )

    assert result["vlanId"] == 4094


# =============================================================================
# update_network Tests
# =============================================================================


@pytest.mark.asyncio
async def test_update_network_name():
    """Test updating network name via Integration API."""
    existing_network = {
        "id": NETWORK_ID,
        "name": "Old Name",
        "vlanId": 10,
        "purpose": "CORPORATE",
    }
    updated_network = {
        "id": NETWORK_ID,
        "name": "New Name",
        "vlanId": 10,
        "purpose": "CORPORATE",
    }

    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=existing_network)
    mock_client.put = AsyncMock(return_value=updated_network)

    with patch_client(mock_client):
        result = await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            name="New Name",
            confirm=True,
        )

    assert result["name"] == "New Name"
    mock_client.put.assert_called_once()

    # Verify GET fetches single network by ID (not listing all)
    get_path = mock_client.get.call_args[0][0]
    assert get_path == f"/integration/v1/sites/{SITE_UUID}/networks/{NETWORK_ID}"

    # Verify PUT sends only changed fields
    put_path = mock_client.put.call_args[0][0]
    assert put_path == f"/integration/v1/sites/{SITE_UUID}/networks/{NETWORK_ID}"
    json_data = mock_client.put.call_args[1]["json_data"]
    assert json_data == {"name": "New Name"}


@pytest.mark.asyncio
async def test_update_network_dhcp():
    """Test updating network DHCP settings via Integration API."""
    existing_network = {"id": NETWORK_ID, "name": "Test Network"}

    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=existing_network)
    mock_client.put = AsyncMock(return_value=existing_network)

    with patch_client(mock_client):
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            dhcp_start="192.168.10.50",
            dhcp_stop="192.168.10.150",
            confirm=True,
        )

    json_data = mock_client.put.call_args[1]["json_data"]
    ip_range = json_data["ipv4Configuration"]["dhcpConfiguration"]["ipAddressRange"]
    assert ip_range["start"] == "192.168.10.50"
    assert ip_range["stop"] == "192.168.10.150"


@pytest.mark.asyncio
async def test_update_network_dry_run():
    """Test update network dry run."""
    result = await update_network(
        site_id=SITE_ID,
        network_id=NETWORK_ID,
        name="Updated Name",
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert "would_update" in result
    assert result["would_update"]["network_id"] == NETWORK_ID
    assert result["would_update"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_network_no_confirm():
    """Test update network fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            name="New Name",
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_network_not_found():
    """Test updating a non-existent network."""
    mock_client = _mock_client()
    mock_client.get = AsyncMock(side_effect=Exception("404 Not Found"))

    with patch_client(mock_client):
        with pytest.raises(ResourceNotFoundError):
            await update_network(
                site_id=SITE_ID,
                network_id="nonexistent",
                name="New Name",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_update_network_not_found_empty_response():
    """Test updating when API returns empty/None."""
    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=None)

    with patch_client(mock_client):
        with pytest.raises(ResourceNotFoundError):
            await update_network(
                site_id=SITE_ID,
                network_id="nonexistent",
                name="New Name",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_update_network_invalid_vlan():
    """Test update network with invalid VLAN ID."""
    with pytest.raises(ValidationError) as excinfo:
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            vlan_id=5000,
            confirm=True,
        )
    assert "vlan" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_network_invalid_purpose():
    """Test update network with invalid purpose."""
    with pytest.raises(ValidationError) as excinfo:
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            purpose="invalid",
            confirm=True,
        )
    assert "purpose" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_network_invalid_subnet():
    """Test update network with invalid subnet format."""
    with pytest.raises(ValidationError) as excinfo:
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            subnet="192.168.10.0",
            confirm=True,
        )
    assert "subnet" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_update_network_multiple_fields():
    """Test updating multiple network fields at once."""
    existing_network = {"id": NETWORK_ID, "name": "Old Name"}
    updated_network = {
        "id": NETWORK_ID,
        "name": "New Name",
        "purpose": "GUEST",
        "vlanId": 20,
    }

    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=existing_network)
    mock_client.put = AsyncMock(return_value=updated_network)

    with patch_client(mock_client):
        result = await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            name="New Name",
            purpose="guest",
            vlan_id=20,
            subnet="192.168.20.0/24",
            dhcp_enabled=False,
            confirm=True,
        )

    assert result["name"] == "New Name"

    json_data = mock_client.put.call_args[1]["json_data"]
    assert json_data["name"] == "New Name"
    assert json_data["purpose"] == "GUEST"
    assert json_data["vlanId"] == 20
    assert json_data["ipv4Configuration"]["hostIpAddress"] == "192.168.20.1"
    assert json_data["ipv4Configuration"]["dhcpConfiguration"]["mode"] == "NONE"


@pytest.mark.asyncio
async def test_update_network_dns_settings():
    """Test updating network DNS settings."""
    existing_network = {"id": NETWORK_ID, "name": "Test Network"}

    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=existing_network)
    mock_client.put = AsyncMock(return_value=existing_network)

    with patch_client(mock_client):
        await update_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            dhcp_dns_1="1.1.1.1",
            dhcp_dns_2="1.0.0.1",
            confirm=True,
        )

    json_data = mock_client.put.call_args[1]["json_data"]
    dns = json_data["ipv4Configuration"]["dhcpConfiguration"]["dnsServerIpAddressesOverride"]
    assert dns == ["1.1.1.1", "1.0.0.1"]


# =============================================================================
# delete_network Tests
# =============================================================================


@pytest.mark.asyncio
async def test_delete_network_success():
    """Test successful network deletion via Integration API."""
    existing_network = {"id": NETWORK_ID, "name": "Delete Me", "vlanId": 10}

    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=existing_network)
    mock_client.delete = AsyncMock(return_value={})

    with patch_client(mock_client):
        result = await delete_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            confirm=True,
        )

    assert result["success"] is True
    assert result["deleted_network_id"] == NETWORK_ID
    mock_client.delete.assert_called_once()

    # Verify Integration API paths
    delete_path = mock_client.delete.call_args[0][0]
    assert delete_path == f"/integration/v1/sites/{SITE_UUID}/networks/{NETWORK_ID}"


@pytest.mark.asyncio
async def test_delete_network_dry_run():
    """Test delete network dry run."""
    result = await delete_network(
        site_id=SITE_ID,
        network_id=NETWORK_ID,
        confirm=True,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["would_delete"] == NETWORK_ID


@pytest.mark.asyncio
async def test_delete_network_no_confirm():
    """Test delete network fails without confirmation."""
    with pytest.raises(ValidationError) as excinfo:
        await delete_network(
            site_id=SITE_ID,
            network_id=NETWORK_ID,
            confirm=False,
        )
    assert "requires confirmation" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_delete_network_not_found():
    """Test deleting a non-existent network."""
    mock_client = _mock_client()
    mock_client.get = AsyncMock(side_effect=Exception("404 Not Found"))

    with patch_client(mock_client):
        with pytest.raises(ResourceNotFoundError):
            await delete_network(
                site_id=SITE_ID,
                network_id="nonexistent",
                confirm=True,
            )


@pytest.mark.asyncio
async def test_delete_network_not_found_empty_response():
    """Test deleting when API returns empty/None."""
    mock_client = _mock_client()
    mock_client.get = AsyncMock(return_value=None)

    with patch_client(mock_client):
        with pytest.raises(ResourceNotFoundError):
            await delete_network(
                site_id=SITE_ID,
                network_id="nonexistent",
                confirm=True,
            )
