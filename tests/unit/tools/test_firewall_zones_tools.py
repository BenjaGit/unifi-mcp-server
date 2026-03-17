"""Tests for firewall_zones tools using pooled clients."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import APIType
from src.utils.exceptions import ValidationError


def make_client(api_type: APIType = APIType.LOCAL) -> AsyncMock:
    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type)
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(
        return_value=SimpleNamespace(name="default", uuid="uuid-default")
    )
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def firewall_zone_client():
    client = make_client()
    with patch("src.tools.firewall_zones.get_network_client", return_value=client):
        yield client


@pytest.fixture
def sample_zones():
    return [
        {"_id": "zone-1", "name": "LAN", "networks": ["net-1"], "networkIds": ["net-1"]},
        {"_id": "zone-2", "name": "IoT", "networks": [], "networkIds": []},
    ]


class TestListFirewallZones:
    @pytest.mark.asyncio
    async def test_success(self, firewall_zone_client, sample_zones):
        from src.tools.firewall_zones import list_firewall_zones

        firewall_zone_client.is_authenticated = False
        firewall_zone_client.get.return_value = {"data": sample_zones}

        result = await list_firewall_zones("default")

        assert len(result) == 2
        firewall_zone_client.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_requires_local(self, firewall_zone_client):
        from src.tools.firewall_zones import list_firewall_zones

        firewall_zone_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(ValidationError):
            await list_firewall_zones("default")


class TestCreateFirewallZone:
    @pytest.mark.asyncio
    async def test_success(self, firewall_zone_client):
        from src.tools.firewall_zones import create_firewall_zone

        firewall_zone_client.is_authenticated = False
        firewall_zone_client.post.return_value = {"data": {"_id": "zone-new", "name": "Guest"}}

        with patch("src.tools.firewall_zones.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await create_firewall_zone("default", "Guest", confirm=True)

        assert result["name"] == "Guest"
        firewall_zone_client.authenticate.assert_awaited_once()
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, firewall_zone_client):
        from src.tools.firewall_zones import create_firewall_zone

        result = await create_firewall_zone("default", "Guest", confirm=True, dry_run=True)

        assert result["dry_run"] is True
        firewall_zone_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self, firewall_zone_client):
        from src.tools.firewall_zones import create_firewall_zone

        with pytest.raises(ValidationError):
            await create_firewall_zone("default", "Guest", confirm=False)


class TestUpdateFirewallZone:
    @pytest.mark.asyncio
    async def test_success(self, firewall_zone_client, sample_zones):
        from src.tools.firewall_zones import update_firewall_zone

        firewall_zone_client.get.return_value = {"data": sample_zones[0]}
        firewall_zone_client.put.return_value = {"data": {"name": "LAN-Updated"}}

        with patch("src.tools.firewall_zones.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await update_firewall_zone(
                "default", "zone-1", name="LAN-Updated", confirm=True
            )

        assert result["name"] == "LAN-Updated"
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, firewall_zone_client, sample_zones):
        from src.tools.firewall_zones import update_firewall_zone

        firewall_zone_client.get.return_value = {"data": sample_zones[0]}

        result = await update_firewall_zone(
            "default", "zone-1", name="LAN", confirm=True, dry_run=True
        )

        assert result["dry_run"] is True
        firewall_zone_client.put.assert_not_called()


class TestAssignNetwork:
    @pytest.mark.asyncio
    async def test_assigns_network(self, firewall_zone_client):
        from src.tools.firewall_zones import assign_network_to_zone

        firewall_zone_client.get.side_effect = [
            {"data": {"networks": []}},
            {"data": {"name": "LAN"}},
        ]

        with patch("src.tools.firewall_zones.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await assign_network_to_zone("default", "zone-1", "net-1", confirm=True)

        assert result["network_id"] == "net-1"
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, firewall_zone_client):
        from src.tools.firewall_zones import assign_network_to_zone

        firewall_zone_client.get.return_value = {"data": {"networks": []}}

        result = await assign_network_to_zone(
            "default",
            "zone-1",
            "net-1",
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True


class TestGetZoneNetworks:
    @pytest.mark.asyncio
    async def test_returns_assignments(self, firewall_zone_client):
        from src.tools.firewall_zones import get_zone_networks

        firewall_zone_client.get.side_effect = [
            {"data": [{"id": "zone-1", "networks": ["net-1"]}]},
            {"data": {"name": "LAN"}},
        ]

        result = await get_zone_networks("default", "zone-1")

        assert result[0]["network_id"] == "net-1"


class TestDeleteFirewallZone:
    @pytest.mark.asyncio
    async def test_success(self, firewall_zone_client):
        from src.tools.firewall_zones import delete_firewall_zone

        with patch("src.tools.firewall_zones.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await delete_firewall_zone("default", "zone-1", confirm=True)

        assert result["status"] == "success"
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, firewall_zone_client):
        from src.tools.firewall_zones import delete_firewall_zone

        result = await delete_firewall_zone("default", "zone-1", confirm=True, dry_run=True)

        assert result["dry_run"] is True


class TestUnassignNetwork:
    @pytest.mark.asyncio
    async def test_unassign(self, firewall_zone_client):
        from src.tools.firewall_zones import unassign_network_from_zone

        firewall_zone_client.get.return_value = {"data": {"networks": ["net-1"]}}

        with patch("src.tools.firewall_zones.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await unassign_network_from_zone("default", "zone-1", "net-1", confirm=True)

        assert result["action"] == "unassigned"
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_assigned_error(self, firewall_zone_client):
        from src.tools.firewall_zones import unassign_network_from_zone

        firewall_zone_client.get.return_value = {"data": {"networks": []}}

        with pytest.raises(ValueError):
            await unassign_network_from_zone("default", "zone-1", "net-1", confirm=True)
