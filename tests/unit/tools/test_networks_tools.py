"""Unit tests for src/tools/networks.py."""

from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.network_client import SiteInfo
from src.tools.networks import (
    get_network_details,
    get_network_references,
    get_network_statistics,
    get_subnet_info,
    list_vlans,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def make_network(
    network_id: str = "net-123",
    name: str = "Default",
    vlan_id: int = 1,
    subnet: str = "192.168.1.0/24",
    dhcp_enabled: bool = True,
) -> dict[str, Any]:
    host_prefix = subnet.rsplit("/", 1)[0].rsplit(".", 1)[0] + ".1"
    network: dict[str, Any] = {
        "id": network_id,
        "name": name,
        "vlanId": vlan_id,
        "purpose": "corporate",
        "ipv4Configuration": {
            "hostIpAddress": host_prefix,
            "prefixLength": int(subnet.rsplit("/", 1)[1]) if "/" in subnet else 24,
            "dhcpConfiguration": {},
        },
    }
    dhcp_config = network["ipv4Configuration"]["dhcpConfiguration"]
    if dhcp_enabled:
        dhcp_config["mode"] = "SERVER"
        dhcp_config["ipAddressRange"] = {"start": "192.168.2.100", "stop": "192.168.1.200"}
        dhcp_config["leaseTimeSeconds"] = 86400
        dhcp_config["dnsServerIpAddressesOverride"] = ["8.8.8.8", "8.8.4.4"]
        dhcp_config["domainName"] = "local"
    else:
        dhcp_config["mode"] = "DISABLED"
    return network


def make_client_on_vlan(vlan_id: int, tx_bytes: int = 1000, rx_bytes: int = 2000) -> dict:
    return {
        "mac": "00:11:22:33:44:55",
        "vlan": vlan_id,
        "tx_bytes": tx_bytes,
        "rx_bytes": rx_bytes,
    }


def create_mock_client(get_responses: list | None = None) -> MagicMock:
    client = MagicMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    if get_responses is None:
        client.get = AsyncMock(return_value=[])
    else:
        client.get = AsyncMock(side_effect=get_responses)
    return client


@contextmanager
def patch_client(mock_client: MagicMock):
    with patch("src.tools.networks.get_network_client", return_value=mock_client):
        yield mock_client


class TestGetNetworkDetails:
    @pytest.mark.asyncio
    async def test_get_network_details_success(self) -> None:
        network_id = "net-123"
        response = make_network(network_id=network_id, name="Main Network")

        with patch_client(create_mock_client([response])):
            result = await get_network_details("site-1", network_id)

        assert result["id"] == network_id
        assert result["name"] == "Main Network"

    @pytest.mark.asyncio
    async def test_get_network_details_not_found(self) -> None:
        with patch_client(create_mock_client([{}])):
            with pytest.raises(ResourceNotFoundError):
                await get_network_details("site-1", "missing")

    @pytest.mark.asyncio
    async def test_get_network_details_raises_on_404(self) -> None:
        mock_client = create_mock_client()
        mock_client.get = AsyncMock(side_effect=Exception("404 Not Found"))

        with patch_client(mock_client):
            with pytest.raises(ResourceNotFoundError):
                await get_network_details("site-1", "missing")

    @pytest.mark.asyncio
    async def test_get_network_details_invalid_site(self) -> None:
        with pytest.raises(ValidationError):
            await get_network_details("", "net-123")


class TestListVlans:
    @pytest.mark.asyncio
    async def test_list_vlans_success(self) -> None:
        response = [
            make_network(network_id="net-1", name="LAN", vlan_id=1),
            make_network(network_id="net-2", name="Guest", vlan_id=100),
        ]

        with patch_client(create_mock_client([response])):
            result = await list_vlans("site-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_vlans_with_pagination(self) -> None:
        response = [make_network(network_id=f"net-{i}", vlan_id=i) for i in range(10)]

        with patch_client(create_mock_client([response])):
            result = await list_vlans("site-1", limit=3, offset=2)

        assert len(result) == 3
        assert result[0]["vlanId"] == 2

    @pytest.mark.asyncio
    async def test_list_vlans_invalid_site(self) -> None:
        with pytest.raises(ValidationError):
            await list_vlans("")


class TestGetSubnetInfo:
    @pytest.mark.asyncio
    async def test_get_subnet_info_success(self) -> None:
        response = make_network(network_id="net-123")

        with patch_client(create_mock_client([response])):
            result = await get_subnet_info("site-1", "net-123")

        assert result["network_id"] == "net-123"
        assert result["dhcpd_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_subnet_info_not_found(self) -> None:
        with patch_client(create_mock_client([{}])):
            with pytest.raises(ResourceNotFoundError):
                await get_subnet_info("site-1", "missing")

    @pytest.mark.asyncio
    async def test_get_subnet_info_invalid_site(self) -> None:
        with pytest.raises(ValidationError):
            await get_subnet_info("", "net-123")


class TestGetNetworkStatistics:
    @pytest.mark.asyncio
    async def test_get_network_statistics_success(self) -> None:
        networks_response = [
            make_network(network_id="net-1", name="LAN", vlan_id=1),
            make_network(network_id="net-2", name="Guest", vlan_id=100),
        ]
        clients_response = {
            "data": [
                make_client_on_vlan(1, 1000, 2000),
                make_client_on_vlan(1, 500, 1000),
                make_client_on_vlan(100, 300, 600),
            ]
        }

        with patch_client(create_mock_client([networks_response, clients_response])):
            result = await get_network_statistics("site-1")

        assert result["site_id"] == "site-1"
        assert len(result["networks"]) == 2
        lan_stats = next(net for net in result["networks"] if net["name"] == "LAN")
        assert lan_stats["client_count"] == 2

    @pytest.mark.asyncio
    async def test_get_network_statistics_invalid_site(self) -> None:
        with pytest.raises(ValidationError):
            await get_network_statistics("")


class TestGetNetworkReferences:
    @pytest.mark.asyncio
    async def test_get_network_references_success(self) -> None:
        api_response = {
            "referenceResources": [
                {
                    "resourceType": "WIFI",
                    "referenceCount": 2,
                    "references": [
                        {"referenceId": "wifi-1"},
                        {"referenceId": "wifi-2"},
                    ],
                }
            ]
        }

        with patch_client(create_mock_client([api_response])):
            result = await get_network_references("site-1", "net-123")

        assert result["network_id"] == "net-123"
        assert result["total_references"] == 2

    @pytest.mark.asyncio
    async def test_get_network_references_not_found(self) -> None:
        with patch_client(create_mock_client([{}])):
            with pytest.raises(ResourceNotFoundError):
                await get_network_references("site-1", "missing")
