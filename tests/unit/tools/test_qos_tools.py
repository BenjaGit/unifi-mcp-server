"""Tests for traffic route tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.qos as qos_module
from src.api.network_client import SiteInfo
from src.tools.qos import (
    create_traffic_route,
    delete_traffic_route,
    list_traffic_routes,
    update_traffic_route,
)
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


def _sample_routes() -> list[dict]:
    return [
        {
            "_id": "route-001",
            "name": "Block External DNS",
            "description": "Block external DNS queries",
            "action": "deny",
            "enabled": True,
            "match_criteria": {"destination_port": 53, "protocol": "udp"},
            "priority": 100,
            "site_id": "default",
        },
        {
            "_id": "route-002",
            "name": "Prioritize VoIP",
            "description": "Mark VoIP with EF",
            "action": "mark",
            "enabled": True,
            "match_criteria": {"destination_port": 5060, "protocol": "udp"},
            "dscp_marking": 46,
            "priority": 50,
            "site_id": "default",
        },
    ]


@pytest.mark.asyncio
async def test_list_traffic_routes_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": _sample_routes()}

    with patch.object(qos_module, "get_network_client", return_value=client):
        result = await list_traffic_routes("default")

    assert len(result) == 2
    assert result[0]["name"] == "Block External DNS"


@pytest.mark.asyncio
async def test_list_traffic_routes_pagination() -> None:
    client = _make_client()
    client.get.return_value = {"data": _sample_routes() * 3}

    with patch.object(qos_module, "get_network_client", return_value=client):
        result = await list_traffic_routes("default", limit=2, offset=2)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_create_traffic_route_success() -> None:
    client = _make_client()
    client.post.return_value = {
        "data": [
            {
                "_id": "route-new",
                "name": "Test Route",
                "action": "allow",
                "enabled": True,
                "match_criteria": {"destination_port": 443, "protocol": "tcp"},
                "priority": 100,
                "site_id": "default",
            }
        ]
    }

    with (
        patch.object(qos_module, "get_network_client", return_value=client),
        patch.object(qos_module, "audit_action", new=AsyncMock()),
    ):
        result = await create_traffic_route(
            site_id="default",
            name="Test Route",
            action="allow",
            destination_port=443,
            protocol="tcp",
            confirm=True,
        )

    assert result["name"] == "Test Route"
    assert result["action"] == "allow"


@pytest.mark.asyncio
async def test_create_traffic_route_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await create_traffic_route(site_id="default", name="Test", action="allow", confirm=False)


@pytest.mark.asyncio
async def test_create_traffic_route_invalid_action() -> None:
    with pytest.raises(ValidationError):
        await create_traffic_route(site_id="default", name="Test", action="invalid", confirm=True)


@pytest.mark.asyncio
async def test_create_traffic_route_invalid_dscp() -> None:
    with pytest.raises(ValidationError):
        await create_traffic_route(
            site_id="default",
            name="Test",
            action="mark",
            dscp_marking=100,
            confirm=True,
        )


@pytest.mark.asyncio
async def test_update_traffic_route_success() -> None:
    client = _make_client()
    updated_route = _sample_routes()[0].copy()
    updated_route["enabled"] = False
    client.put.return_value = {"data": [updated_route]}

    with (
        patch.object(qos_module, "get_network_client", return_value=client),
        patch.object(qos_module, "audit_action", new=AsyncMock()),
    ):
        result = await update_traffic_route(
            site_id="default",
            route_id="route-001",
            enabled=False,
            confirm=True,
        )

    assert result["enabled"] is False


@pytest.mark.asyncio
async def test_update_traffic_route_no_fields() -> None:
    with pytest.raises(ValidationError):
        await update_traffic_route(site_id="default", route_id="route-001", confirm=True)


@pytest.mark.asyncio
async def test_update_traffic_route_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await update_traffic_route(
            site_id="default",
            route_id="route-001",
            enabled=False,
            confirm=False,
        )


@pytest.mark.asyncio
async def test_delete_traffic_route_success() -> None:
    client = _make_client()

    with (
        patch.object(qos_module, "get_network_client", return_value=client),
        patch.object(qos_module, "audit_action", new=AsyncMock()),
    ):
        result = await delete_traffic_route(site_id="default", route_id="route-001", confirm=True)

    assert result["success"] is True
    assert result["route_id"] == "route-001"


@pytest.mark.asyncio
async def test_delete_traffic_route_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await delete_traffic_route(site_id="default", route_id="route-001", confirm=False)
