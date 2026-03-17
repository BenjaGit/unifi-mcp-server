"""Unit tests for traffic rules v2 tools using pooled clients."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import APIType
from src.tools.traffic_rules import (
    create_traffic_rule,
    delete_traffic_rule,
    list_traffic_rules,
    update_traffic_rule,
)
from src.utils.exceptions import ValidationError


def make_client(api_type: APIType = APIType.LOCAL) -> AsyncMock:
    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type)
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(
        return_value=SimpleNamespace(name="default", uuid="uuid-default")
    )
    client.v2_path = MagicMock(side_effect=lambda site, ep: f"/v2/api/site/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def traffic_client():
    client = make_client()
    with patch("src.tools.traffic_rules.get_network_client", return_value=client):
        yield client


@pytest.fixture
def cloud_client():
    client = make_client(api_type=APIType.CLOUD_V1)
    with patch("src.tools.traffic_rules.get_network_client", return_value=client):
        yield client


SAMPLE_RULES = [
    {"_id": "rule1", "description": "Block YouTube", "action": "BLOCK", "enabled": True},
    {"_id": "rule2", "description": "Limit Netflix", "action": "THROTTLE", "enabled": False},
]


class TestListTrafficRules:
    @pytest.mark.asyncio
    async def test_success(self, traffic_client):

        traffic_client.get.return_value = SAMPLE_RULES

        result = await list_traffic_rules("default")

        assert len(result) == 2
        traffic_client.v2_path.assert_called_once_with("default", "trafficrules")

    @pytest.mark.asyncio
    async def test_requires_local(self, cloud_client):

        with pytest.raises(NotImplementedError):
            await list_traffic_rules("default")


class TestCreateTrafficRule:
    @pytest.mark.asyncio
    async def test_success(self, traffic_client):
        traffic_client.post.return_value = {"_id": "new-rule"}

        with patch("src.tools.traffic_rules.log_audit", new_callable=AsyncMock) as mock_audit:
            result = await create_traffic_rule("default", {"action": "BLOCK"}, confirm=True)

        assert result["_id"] == "new-rule"
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, traffic_client):
        result = await create_traffic_rule(
            "default", {"action": "BLOCK"}, confirm=True, dry_run=True
        )

        assert result["dry_run"] is True
        traffic_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self, traffic_client):
        with pytest.raises(ValidationError):
            await create_traffic_rule("default", {"action": "BLOCK"}, confirm=False)

    @pytest.mark.asyncio
    async def test_cloud_rejected(self, cloud_client):
        with pytest.raises(NotImplementedError):
            await create_traffic_rule("default", {"action": "BLOCK"}, confirm=True)


class TestUpdateTrafficRule:
    @pytest.mark.asyncio
    async def test_success(self, traffic_client):
        traffic_client.put.return_value = {"_id": "rule1", "enabled": False}

        with patch("src.tools.traffic_rules.log_audit", new_callable=AsyncMock) as mock_audit:
            result = await update_traffic_rule("default", "rule1", {"enabled": False}, confirm=True)

        assert result["enabled"] is False
        traffic_client.v2_path.assert_called_with("default", "trafficrules/rule1")
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, traffic_client):
        result = await update_traffic_rule("default", "rule1", {}, confirm=True, dry_run=True)

        assert result["dry_run"] is True
        traffic_client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self, traffic_client):
        with pytest.raises(ValidationError):
            await update_traffic_rule("default", "rule1", {}, confirm=False)


class TestDeleteTrafficRule:
    @pytest.mark.asyncio
    async def test_success(self, traffic_client):
        with patch("src.tools.traffic_rules.log_audit", new_callable=AsyncMock) as mock_audit:
            result = await delete_traffic_rule("default", "rule1", confirm=True)

        assert result["success"] is True
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, traffic_client):
        result = await delete_traffic_rule("default", "rule1", confirm=True, dry_run=True)

        assert result["dry_run"] is True
        traffic_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self, traffic_client):
        with pytest.raises(ValidationError):
            await delete_traffic_rule("default", "rule1", confirm=False)
