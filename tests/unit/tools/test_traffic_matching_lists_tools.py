"""Tests for traffic matching lists tools using pooled clients."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.traffic_matching_lists import (
    create_traffic_matching_list,
    delete_traffic_matching_list,
    get_traffic_matching_list,
    list_traffic_matching_lists,
    update_traffic_matching_list,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def make_client() -> AsyncMock:
    client = AsyncMock()
    client.settings = SimpleNamespace()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(
        return_value=SimpleNamespace(name="default", uuid="uuid-default")
    )
    from unittest.mock import MagicMock

    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def tml_client():
    client = make_client()
    with patch("src.tools.traffic_matching_lists.get_network_client", return_value=client):
        yield client


class TestListTrafficMatchingLists:
    @pytest.mark.asyncio
    async def test_success(self, tml_client):
        tml_client.get.return_value = {
            "data": [
                {"_id": "tml-1", "type": "PORTS", "name": "Web", "items": ["80"]},
                {"_id": "tml-2", "type": "IPV4_ADDRESSES", "name": "IPs", "items": ["10.0.0.1"]},
            ]
        }

        result = await list_traffic_matching_lists("default", limit=10, offset=0)

        assert len(result) == 2
        tml_client.integration_path.assert_called_once()


class TestGetTrafficMatchingList:
    @pytest.mark.asyncio
    async def test_success(self, tml_client):
        tml_client.get.return_value = {"data": {"_id": "tml-1", "type": "PORTS", "name": "Web"}}

        result = await get_traffic_matching_list("default", "tml-1")

        assert result["id"] == "tml-1"

    @pytest.mark.asyncio
    async def test_not_found(self, tml_client):
        tml_client.get.return_value = {"data": None}

        with pytest.raises(ResourceNotFoundError):
            await get_traffic_matching_list("default", "missing")


class TestCreateTrafficMatchingList:
    @pytest.mark.asyncio
    async def test_success(self, tml_client):
        tml_client.post.return_value = {"_id": "tml-3", "name": "New"}

        with patch(
            "src.tools.traffic_matching_lists.log_audit", new_callable=AsyncMock
        ) as mock_audit:
            result = await create_traffic_matching_list(
                "default",
                "PORTS",
                "New",
                ["80"],
                confirm=True,
            )

        assert result["name"] == "New"
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, tml_client):
        result = await create_traffic_matching_list(
            "default", "PORTS", "New", ["80"], confirm=True, dry_run=True
        )

        assert result["dry_run"] is True
        tml_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_validations(self, tml_client):
        with pytest.raises(ValidationError):
            await create_traffic_matching_list("default", "PORTS", "New", [], confirm=True)


class TestUpdateTrafficMatchingList:
    @pytest.mark.asyncio
    async def test_success(self, tml_client):
        tml_client.get.return_value = {"data": {"_id": "tml-1", "type": "PORTS", "name": "Old"}}
        tml_client.put.return_value = {"data": {"_id": "tml-1", "name": "Updated"}}

        with patch(
            "src.tools.traffic_matching_lists.log_audit", new_callable=AsyncMock
        ) as mock_audit:
            result = await update_traffic_matching_list(
                "default",
                "tml-1",
                name="Updated",
                confirm=True,
            )

        assert result["name"] == "Updated"
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, tml_client):
        result = await update_traffic_matching_list(
            "default",
            "tml-1",
            name="Updated",
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True
        tml_client.put.assert_not_called()


class TestDeleteTrafficMatchingList:
    @pytest.mark.asyncio
    async def test_success(self, tml_client):
        tml_client.get.return_value = {"data": {"_id": "tml-1"}}

        with patch(
            "src.tools.traffic_matching_lists.log_audit", new_callable=AsyncMock
        ) as mock_audit:
            result = await delete_traffic_matching_list("default", "tml-1", confirm=True)

        assert result["success"] is True
        mock_audit.assert_awaited()

    @pytest.mark.asyncio
    async def test_dry_run(self, tml_client):
        with patch("src.tools.traffic_matching_lists.log_audit", new_callable=AsyncMock):
            result = await delete_traffic_matching_list(
                "default", "tml-1", confirm=True, dry_run=True
            )

        assert result["dry_run"] is True
        tml_client.delete.assert_not_called()
