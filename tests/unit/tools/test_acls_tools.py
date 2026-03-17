"""Tests for ACL tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.acls as acls_module
from src.api.network_client import SiteInfo
from src.tools.acls import (
    create_acl_rule,
    delete_acl_rule,
    get_acl_rule,
    get_acl_rule_ordering,
    list_acl_rules,
    update_acl_rule,
    update_acl_rule_ordering,
)
from src.utils.exceptions import ValidationError


def _make_client() -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.integration_path = MagicMock(
        side_effect=lambda site_uuid, ep: f"/integration/v1/sites/{site_uuid}/{ep}"
    )
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_acl_rules_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": [{"_id": "acl-1", "site_id": "default", "name": "Allow DNS", "action": "allow"}]
    }

    with patch.object(acls_module, "get_network_client", return_value=client):
        result = await list_acl_rules("default")

    assert len(result) == 1
    assert result[0]["id"] == "acl-1"


@pytest.mark.asyncio
async def test_get_acl_rule_success() -> None:
    client = _make_client()
    client.get.return_value = {
        "data": {"_id": "acl-1", "site_id": "default", "name": "Allow DNS", "action": "allow"}
    }

    with patch.object(acls_module, "get_network_client", return_value=client):
        result = await get_acl_rule("default", "acl-1")

    assert result["id"] == "acl-1"
    client.get.assert_awaited_once_with("/integration/v1/sites/uuid-default/acl-rules/acl-1")


@pytest.mark.asyncio
async def test_create_acl_rule_dry_run() -> None:
    client = _make_client()

    with patch.object(acls_module, "get_network_client", return_value=client):
        result = await create_acl_rule("default", "Block IoT", "deny", confirm=True, dry_run=True)

    assert result["dry_run"] is True
    assert result["payload"]["name"] == "Block IoT"
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_create_acl_rule_no_confirm() -> None:
    with pytest.raises(ValidationError):
        await create_acl_rule("default", "Block IoT", "deny", confirm=False)


@pytest.mark.asyncio
async def test_update_acl_rule_success() -> None:
    client = _make_client()
    client.put.return_value = {
        "data": {"_id": "acl-1", "site_id": "default", "name": "Updated", "action": "allow"}
    }

    with (
        patch.object(acls_module, "get_network_client", return_value=client),
        patch.object(acls_module, "audit_action", new=AsyncMock()),
    ):
        result = await update_acl_rule("default", "acl-1", name="Updated", confirm=True)

    assert result["name"] == "Updated"
    client.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_acl_rule_success() -> None:
    client = _make_client()

    with (
        patch.object(acls_module, "get_network_client", return_value=client),
        patch.object(acls_module, "audit_action", new=AsyncMock()),
    ):
        result = await delete_acl_rule("default", "acl-1", confirm=True)

    assert result["success"] is True
    client.delete.assert_awaited_once_with("/integration/v1/sites/uuid-default/acl-rules/acl-1")


@pytest.mark.asyncio
async def test_get_acl_rule_ordering() -> None:
    client = _make_client()
    client.get.return_value = {"orderedAclRuleIds": ["acl-1", "acl-2"]}

    with patch.object(acls_module, "get_network_client", return_value=client):
        result = await get_acl_rule_ordering("default")

    assert result["orderedAclRuleIds"] == ["acl-1", "acl-2"]


@pytest.mark.asyncio
async def test_update_acl_rule_ordering_dry_run() -> None:
    client = _make_client()

    with patch.object(acls_module, "get_network_client", return_value=client):
        result = await update_acl_rule_ordering(
            "default", ["acl-1", "acl-2"], confirm=True, dry_run=True
        )

    assert result["dry_run"] is True
    client.put.assert_not_called()
