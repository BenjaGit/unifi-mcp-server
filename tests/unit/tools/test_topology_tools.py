"""Tests for topology tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.topology as topology_module
from src.api.network_client import SiteInfo
from src.tools.topology import (
    export_topology,
    get_device_connections,
    get_network_topology,
    get_port_mappings,
    get_topology_statistics,
)
from src.utils.exceptions import ValidationError


def _make_client(device_data: list[dict], client_data: list[dict]) -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.integration_path = MagicMock(
        side_effect=lambda site_uuid, ep: f"/integration/v1/sites/{site_uuid}/{ep}"
    )

    async def _get(url: str):
        if "devices" in url:
            return device_data
        if "clients" in url:
            return client_data
        return []

    client.get = AsyncMock(side_effect=_get)
    return client


@pytest.fixture
def sample_device_data() -> list[dict]:
    return [
        {
            "id": "gateway_001",
            "macAddress": "aa:bb:cc:dd:ee:01",
            "name": "UDM Pro",
            "model": "UDM-Pro",
            "type": "ugw",
            "ipAddress": "192.168.2.1",
            "state": "CONNECTED",
            "adopted": True,
        },
        {
            "id": "switch_001",
            "macAddress": "aa:bb:cc:dd:ee:02",
            "name": "USW-24-POE",
            "model": "USW-24-POE",
            "type": "usw",
            "ipAddress": "192.168.1.2",
            "state": "CONNECTED",
            "adopted": True,
            "uplink": {"deviceId": "gateway_001", "portIndex": 1, "speedMbps": 1000},
        },
    ]


@pytest.fixture
def sample_client_data() -> list[dict]:
    return [
        {
            "id": "client_001",
            "macAddress": "11:22:33:44:55:01",
            "name": "iPhone",
            "ipAddress": "192.168.2.100",
            "type": "WIRELESS",
            "uplinkDeviceId": "switch_001",
        }
    ]


@pytest.mark.asyncio
async def test_get_network_topology_success(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await get_network_topology("default")

    assert result["site_id"] == "uuid-default"
    assert result["total_devices"] == 2
    assert result["total_clients"] == 1
    assert result["total_connections"] >= 1


@pytest.mark.asyncio
async def test_get_network_topology_authenticates_when_needed(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    client.is_authenticated = False

    with patch.object(topology_module, "get_network_client", return_value=client):
        await get_network_topology("default")

    client.authenticate.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_network_topology_include_coordinates_flag(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await get_network_topology("default", include_coordinates=True)

    assert result["has_coordinates"] is True


@pytest.mark.asyncio
async def test_get_device_connections_filters_by_device(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await get_device_connections("default", "switch_001")

    assert result
    assert all(
        conn["source_node_id"] == "switch_001" or conn["target_node_id"] == "switch_001"
        for conn in result
    )


@pytest.mark.asyncio
async def test_get_port_mappings(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await get_port_mappings("default", "switch_001")

    assert result["device_id"] == "switch_001"
    assert isinstance(result["ports"], dict)


@pytest.mark.asyncio
async def test_export_topology_json(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await export_topology("default", "json")

    assert result.startswith("{")
    assert '"nodes"' in result


@pytest.mark.asyncio
async def test_export_topology_graphml(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await export_topology("default", "graphml")

    assert "<graphml" in result


@pytest.mark.asyncio
async def test_export_topology_dot(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await export_topology("default", "dot")

    assert "digraph" in result


@pytest.mark.asyncio
async def test_export_topology_invalid_format() -> None:
    with pytest.raises(ValidationError):
        await export_topology("default", "invalid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_topology_statistics(
    sample_device_data: list[dict], sample_client_data: list[dict]
) -> None:
    client = _make_client(sample_device_data, sample_client_data)
    with patch.object(topology_module, "get_network_client", return_value=client):
        result = await get_topology_statistics("default")

    assert result["site_id"] == "uuid-default"
    assert result["total_devices"] == 2
    assert result["total_clients"] == 1
