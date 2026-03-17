"""Unit tests for application tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.application as app_module
from src.tools.application import get_application_info


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_get_application_info_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": {
            "version": "8.4.59",
            "build": "atag_8.4.59_12345",
            "deploymentType": "standalone",
            "capabilities": ["network", "protect"],
            "systemInfo": {"hostname": "unifi-controller"},
        }
    }

    with patch.object(app_module, "get_network_client", return_value=client):
        result = await get_application_info()

    assert result["version"] == "8.4.59"
    assert result["deployment_type"] == "standalone"
    assert result["system_info"]["hostname"] == "unifi-controller"
    client.get.assert_awaited_once_with("/integration/v1/info")


@pytest.mark.asyncio
async def test_get_application_info_authenticates_when_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": {"version": "8.5.0"}}

    with patch.object(app_module, "get_network_client", return_value=client):
        result = await get_application_info()

    client.authenticate.assert_awaited_once()
    assert result["version"] == "8.5.0"


@pytest.mark.asyncio
async def test_get_application_info_minimal_response() -> None:
    client = _make_client()
    client.get.return_value = {"version": "8.0.0", "build": None}

    with patch.object(app_module, "get_network_client", return_value=client):
        result = await get_application_info()

    assert result["version"] == "8.0.0"
    assert result["build"] is None
    assert result["capabilities"] == []
    assert result["system_info"] == {}


@pytest.mark.asyncio
async def test_get_application_info_fallback_raw() -> None:
    client = _make_client()
    client.get.return_value = ["unexpected"]

    with patch.object(app_module, "get_network_client", return_value=client):
        result = await get_application_info()

    assert result == {"raw": ["unexpected"]}
