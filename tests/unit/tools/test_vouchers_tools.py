"""Unit tests for voucher management tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.vouchers as vouchers_module
from src.api.network_client import SiteInfo
from src.tools.vouchers import (
    bulk_delete_vouchers,
    create_vouchers,
    delete_voucher,
    get_voucher,
    list_vouchers,
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
    return client


def _sample_voucher(voucher_id: str = "voucher1", code: str = "ABCD-1234-EFGH") -> dict:
    return {
        "_id": voucher_id,
        "site_id": "default",
        "code": code,
        "status": "unused",
        "used": 0,
        "quota": 1,
        "duration": 3600,
        "create_time": "2026-01-05T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_list_vouchers_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [_sample_voucher(), _sample_voucher(voucher_id="voucher2", code="WXYZ-5678")]
    }

    with patch.object(vouchers_module, "get_network_client", return_value=client):
        result = await list_vouchers("default")

    assert len(result) == 2
    assert result[0]["code"] == "ABCD-1234-EFGH"


@pytest.mark.asyncio
async def test_list_vouchers_with_filter_and_pagination() -> None:
    client = _make_client()
    client.get.return_value = {"data": [_sample_voucher()]}

    with patch.object(vouchers_module, "get_network_client", return_value=client):
        await list_vouchers("default", limit=10, offset=5, filter_expr="status==unused")

    params = client.get.call_args.kwargs["params"]
    assert params["limit"] == 10
    assert params["offset"] == 5
    assert params["filter"] == "status==unused"


@pytest.mark.asyncio
async def test_list_vouchers_authenticates_if_needed() -> None:
    client = _make_client()
    client.is_authenticated = False
    client.get.return_value = {"data": [_sample_voucher()]}

    with patch.object(vouchers_module, "get_network_client", return_value=client):
        await list_vouchers("default")

    client.authenticate.assert_called_once()


@pytest.mark.asyncio
async def test_get_voucher_success() -> None:
    client = _make_client()
    client.get.return_value = {"data": [_sample_voucher()]}

    with patch.object(vouchers_module, "get_network_client", return_value=client):
        result = await get_voucher("default", "voucher1")

    assert result["code"] == "ABCD-1234-EFGH"


@pytest.mark.asyncio
async def test_get_voucher_not_found() -> None:
    client = _make_client()
    client.get.return_value = {"data": [_sample_voucher()]}

    with patch.object(vouchers_module, "get_network_client", return_value=client):
        with pytest.raises(ValueError):
            await get_voucher("default", "missing")


@pytest.mark.asyncio
async def test_create_vouchers_success() -> None:
    client = _make_client()
    client.post.return_value = {
        "data": [
            _sample_voucher(voucher_id="new1", code="NEW1-CODE"),
            _sample_voucher(voucher_id="new2", code="NEW2-CODE"),
        ]
    }

    with (
        patch.object(vouchers_module, "get_network_client", return_value=client),
        patch.object(vouchers_module, "audit_action", new=AsyncMock()),
    ):
        result = await create_vouchers("default", 2, 3600, confirm=True)

    assert result["success"] is True
    assert result["count"] == 2
    assert len(result["vouchers"]) == 2


@pytest.mark.asyncio
async def test_create_vouchers_with_limits_and_note() -> None:
    client = _make_client()
    client.post.return_value = {"data": []}

    with (
        patch.object(vouchers_module, "get_network_client", return_value=client),
        patch.object(vouchers_module, "audit_action", new=AsyncMock()),
    ):
        await create_vouchers(
            "default",
            5,
            7200,
            upload_limit_kbps=1000,
            download_limit_kbps=5000,
            download_quota_mb=1000,
            note="Test vouchers",
            confirm=True,
        )

    payload = client.post.call_args.kwargs["json_data"]
    assert payload["cmd"] == "create-voucher"
    assert payload["n"] == 5
    assert payload["up"] == 1000
    assert payload["down"] == 5000
    assert payload["bytes"] == 1000
    assert payload["note"] == "Test vouchers"


@pytest.mark.asyncio
async def test_create_vouchers_dry_run() -> None:
    with patch.object(vouchers_module, "get_network_client", return_value=_make_client()):
        result = await create_vouchers("default", 3, 3600, confirm=True, dry_run=True)

    assert result["dry_run"] is True
    assert result["payload"]["n"] == 3


@pytest.mark.asyncio
async def test_create_vouchers_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await create_vouchers("default", 1, 3600, confirm=False)


@pytest.mark.asyncio
async def test_delete_voucher_success() -> None:
    client = _make_client()

    with (
        patch.object(vouchers_module, "get_network_client", return_value=client),
        patch.object(vouchers_module, "audit_action", new=AsyncMock()),
    ):
        result = await delete_voucher("default", "voucher1", confirm=True)

    assert result["success"] is True
    client.post.assert_called_once_with(
        "/proxy/network/api/s/default/cmd/hotspot",
        json_data={"cmd": "delete-voucher", "_id": "voucher1"},
    )


@pytest.mark.asyncio
async def test_delete_voucher_dry_run() -> None:
    with patch.object(vouchers_module, "get_network_client", return_value=_make_client()):
        result = await delete_voucher("default", "voucher1", confirm=True, dry_run=True)

    assert result["dry_run"] is True
    assert result["voucher_id"] == "voucher1"


@pytest.mark.asyncio
async def test_delete_voucher_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        await delete_voucher("default", "voucher1", confirm=False)


@pytest.mark.asyncio
async def test_bulk_delete_vouchers_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [
            {"_id": "v1", "status": "expired"},
            {"_id": "v2", "status": "expired"},
            {"_id": "v3", "status": "unused"},
        ]
    }

    with (
        patch.object(vouchers_module, "get_network_client", return_value=client),
        patch.object(vouchers_module, "audit_action", new=AsyncMock()),
    ):
        result = await bulk_delete_vouchers("default", "status==expired", confirm=True)

    assert result["success"] is True
    assert result["deleted_count"] == 2


@pytest.mark.asyncio
async def test_bulk_delete_vouchers_dry_run_and_requires_confirmation() -> None:
    with patch.object(vouchers_module, "get_network_client", return_value=_make_client()):
        dry_result = await bulk_delete_vouchers(
            "default", "status==unused", confirm=True, dry_run=True
        )
    assert dry_result["dry_run"] is True

    with pytest.raises(ValidationError):
        await bulk_delete_vouchers("default", "status==expired", confirm=False)
