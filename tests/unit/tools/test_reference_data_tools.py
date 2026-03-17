"""Unit tests for reference data tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.reference_data as ref_module
from src.api.network_client import SiteInfo
from src.tools.reference_data import list_countries, list_device_tags, list_radius_profiles


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.integration_path = MagicMock(
        side_effect=lambda site_uuid, ep: f"/integration/v1/sites/{site_uuid}/{ep}"
    )
    client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_countries_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "us", "code": "US", "name": "United States"},
            {"_id": "ca", "code": "CA", "name": "Canada"},
        ]
    }

    with patch.object(ref_module, "get_network_client", return_value=client):
        result = await list_countries(limit=1, offset=0)

    assert len(result) == 1
    assert result[0]["code"] == "US"
    client.get.assert_awaited_once_with("/integration/v1/countries")


@pytest.mark.asyncio
async def test_list_device_tags_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "tag1", "name": "Access Point"},
            {"_id": "tag2", "name": "Switch"},
        ]
    }

    with patch.object(ref_module, "get_network_client", return_value=client):
        result = await list_device_tags("default", limit=10, offset=0)

    assert len(result) == 2
    assert result[1]["name"] == "Switch"


@pytest.mark.asyncio
async def test_list_radius_profiles_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "radius1", "name": "Corporate"},
            {"_id": "radius2", "name": "Guest"},
        ]
    }

    with patch.object(ref_module, "get_network_client", return_value=client):
        result = await list_radius_profiles("default")

    assert len(result) == 2
    assert result[0]["name"] == "Corporate"


@pytest.mark.asyncio
async def test_reference_tools_authenticate_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": []}

    with patch.object(ref_module, "get_network_client", return_value=client):
        await list_device_tags("default")

    client.authenticate.assert_awaited_once()
