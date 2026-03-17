"""Unit tests for port forwarding tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.port_forwarding as pf_module
from src.api.network_client import SiteInfo
from src.tools.port_forwarding import create_port_forward, delete_port_forward, list_port_forwards
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_port_forwards_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "pf1", "name": "HTTP", "dst_port": "80", "fwd": "192.168.2.100"},
            {"_id": "pf2", "name": "SSH", "dst_port": "22", "fwd": "192.168.2.100"},
        ]
    }

    with patch.object(pf_module, "get_network_client", return_value=client):
        result = await list_port_forwards("default")

    assert len(result) == 2
    assert result[0]["name"] == "HTTP"


@pytest.mark.asyncio
async def test_list_port_forwards_pagination() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": f"pf{i}", "name": f"Rule {i}"} for i in range(10)]}

    with patch.object(pf_module, "get_network_client", return_value=client):
        result = await list_port_forwards("default", limit=3, offset=2)

    assert len(result) == 3
    assert result[0]["_id"] == "pf2"


@pytest.mark.asyncio
async def test_list_port_forwards_empty() -> None:
    client = _make_client()
    client.get.return_value = {"data": []}

    with patch.object(pf_module, "get_network_client", return_value=client):
        result = await list_port_forwards("default")

    assert result == []


@pytest.mark.asyncio
async def test_create_port_forward_success() -> None:
    client = _make_client()
    client.post.return_value = {
        "data": [
            {
                "_id": "new_pf1",
                "name": "Web Server",
                "dst_port": "80",
                "fwd": "192.168.2.100",
                "fwd_port": "80",
                "proto": "tcp",
            }
        ]
    }

    with (
        patch.object(pf_module, "get_network_client", return_value=client),
        patch.object(pf_module, "log_audit", new=AsyncMock()),
    ):
        result = await create_port_forward(
            site_id="default",
            name="Web Server",
            dst_port=80,
            fwd_ip="192.168.2.100",
            fwd_port=80,
            protocol="tcp",
            confirm=True,
        )

    assert result["_id"] == "new_pf1"
    assert client.post.call_args.kwargs["json_data"]["proto"] == "tcp"


@pytest.mark.asyncio
async def test_create_port_forward_dry_run() -> None:
    with patch.object(pf_module, "log_audit", new=AsyncMock()):
        result = await create_port_forward(
            site_id="default",
            name="Test Rule",
            dst_port=443,
            fwd_ip="192.168.2.10",
            fwd_port=443,
            confirm=True,
            dry_run=True,
        )

    assert result["dry_run"] is True
    assert result["would_create"]["name"] == "Test Rule"


@pytest.mark.asyncio
async def test_create_port_forward_requires_confirm() -> None:
    with pytest.raises(ValidationError):
        await create_port_forward(
            site_id="default",
            name="Test",
            dst_port=80,
            fwd_ip="192.168.2.1",
            fwd_port=80,
            confirm=False,
        )


@pytest.mark.asyncio
async def test_create_port_forward_validates_protocol() -> None:
    with pytest.raises(ValidationError):
        await create_port_forward(
            site_id="default",
            name="Test",
            dst_port=80,
            fwd_ip="192.168.2.1",
            fwd_port=80,
            protocol="invalid",
            confirm=True,
        )


@pytest.mark.asyncio
async def test_create_port_forward_validates_port() -> None:
    with pytest.raises(ValidationError):
        await create_port_forward(
            site_id="default",
            name="Test",
            dst_port=99999,
            fwd_ip="192.168.2.1",
            fwd_port=80,
            confirm=True,
        )


@pytest.mark.asyncio
async def test_create_port_forward_validates_ip() -> None:
    with pytest.raises(ValidationError):
        await create_port_forward(
            site_id="default",
            name="Test",
            dst_port=80,
            fwd_ip="invalid-ip",
            fwd_port=80,
            confirm=True,
        )


@pytest.mark.asyncio
async def test_create_port_forward_includes_src_and_log() -> None:
    client = _make_client()
    client.post.return_value = {"data": [{"_id": "pf1", "name": "Restricted"}]}

    with (
        patch.object(pf_module, "get_network_client", return_value=client),
        patch.object(pf_module, "log_audit", new=AsyncMock()),
    ):
        await create_port_forward(
            site_id="default",
            name="Restricted",
            dst_port=22,
            fwd_ip="192.168.2.1",
            fwd_port=22,
            src="10.0.0.0/24",
            log=True,
            confirm=True,
        )

    payload = client.post.call_args.kwargs["json_data"]
    assert payload["src"] == "10.0.0.0/24"
    assert payload["log"] is True


@pytest.mark.asyncio
async def test_delete_port_forward_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [{"_id": "pf1", "name": "Test Rule"}]}
    client.delete.return_value = {}

    with (
        patch.object(pf_module, "get_network_client", return_value=client),
        patch.object(pf_module, "log_audit", new=AsyncMock()),
    ):
        result = await delete_port_forward("default", "pf1", confirm=True)

    assert result["success"] is True
    assert result["deleted_rule_id"] == "pf1"


@pytest.mark.asyncio
async def test_delete_port_forward_dry_run() -> None:
    with patch.object(pf_module, "log_audit", new=AsyncMock()):
        result = await delete_port_forward("default", "pf1", confirm=True, dry_run=True)

    assert result["dry_run"] is True
    assert result["would_delete"] == "pf1"


@pytest.mark.asyncio
async def test_delete_port_forward_not_found() -> None:
    client = _make_client()
    client.get.return_value = {"data": []}

    with (
        patch.object(pf_module, "get_network_client", return_value=client),
        patch.object(pf_module, "log_audit", new=AsyncMock()),
    ):
        with pytest.raises(ResourceNotFoundError):
            await delete_port_forward("default", "nonexistent", confirm=True)


@pytest.mark.asyncio
async def test_delete_port_forward_requires_confirm() -> None:
    with pytest.raises(ValidationError):
        await delete_port_forward("default", "pf1", confirm=False)
