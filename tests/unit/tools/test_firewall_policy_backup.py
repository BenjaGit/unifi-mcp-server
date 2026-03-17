"""Unit tests for firewall policy backup/restore tools."""

import asyncio
import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Provide a lightweight fastmcp stub when the dependency is unavailable.
try:  # pragma: no cover - executed only when fastmcp is missing
    import fastmcp  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    import sys

    providers_module = ModuleType("fastmcp.server.providers")

    class LocalProvider:
        def tool(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

    providers_module.LocalProvider = LocalProvider  # type: ignore[attr-defined]

    server_module = ModuleType("fastmcp.server")
    server_module.providers = providers_module  # type: ignore[attr-defined]

    fastmcp_module = ModuleType("fastmcp")
    fastmcp_module.server = server_module  # type: ignore[attr-defined]

    sys.modules.setdefault("fastmcp", fastmcp_module)
    sys.modules.setdefault("fastmcp.server", server_module)
    sys.modules.setdefault("fastmcp.server.providers", providers_module)

from src.config.config import APIType
from src.utils.exceptions import ValidationError


def run(coro):
    """Execute an async coroutine synchronously for tests."""

    return asyncio.run(coro)


def make_mock_client(
    *,
    api_type: APIType = APIType.LOCAL,
    site_name: str = "default",
    site_uuid: str = "uuid-default",
) -> AsyncMock:
    """Create a reusable mock NetworkClient instance."""

    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type)
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SimpleNamespace(name=site_name, uuid=site_uuid))
    client.v2_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/v2/api/site/{site}/{ep}"
    )
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def firewall_client() -> Generator[AsyncMock, None, None]:
    """Provide a patched pooled client for firewall policy backup tools."""

    client = make_mock_client()
    with patch("src.tools.firewall_policy_backup.get_network_client", return_value=client):
        yield client


@pytest.fixture
def raw_policies() -> list[dict]:
    return [
        {
            "_id": "policy-1",
            "name": "Block IOT",
            "action": "BLOCK",
            "enabled": True,
            "predefined": False,
            "site_id": "site-abc",
            "create_time": 1710000000,
            "update_time": 1710000001,
            "origin_id": "pf-123",
            "origin_type": "port_forward",
            "protocol": "all",
            "ip_version": "BOTH",
            "connection_state_type": "ALL",
            "source": {"zone_id": "zone-a", "matching_target": "ANY"},
            "destination": {"zone_id": "zone-b", "matching_target": "ANY"},
        },
        {
            "_id": "policy-2",
            "name": "Allow LAN",
            "action": "ALLOW",
            "enabled": True,
            "predefined": False,
            "site_id": "site-abc",
            "create_time": 1710000002,
            "update_time": 1710000003,
            "protocol": "tcp",
            "ip_version": "BOTH",
            "connection_state_type": "ALL",
            "source": {"zone_id": "zone-c", "matching_target": "NETWORK"},
            "destination": {"zone_id": "zone-d", "matching_target": "NETWORK"},
        },
        {
            "_id": "policy-sys",
            "name": "System Default",
            "action": "ALLOW",
            "enabled": True,
            "predefined": True,
            "site_id": "site-abc",
            "create_time": 1700000000,
            "update_time": 1700000000,
            "protocol": "all",
            "ip_version": "BOTH",
            "connection_state_type": "ALL",
            "source": {"zone_id": "zone-a", "matching_target": "ANY"},
            "destination": {"zone_id": "zone-a", "matching_target": "ANY"},
        },
    ]


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestConflictStrategy:
    """Tests for ConflictStrategy enum."""

    def test_values(self) -> None:
        from src.models.firewall_policy import ConflictStrategy

        assert ConflictStrategy.SKIP == "SKIP"
        assert ConflictStrategy.OVERWRITE == "OVERWRITE"
        assert ConflictStrategy.FAIL == "FAIL"

    def test_case_insensitive_lookup(self) -> None:
        from src.models.firewall_policy import ConflictStrategy

        assert ConflictStrategy("SKIP") == ConflictStrategy.SKIP
        assert ConflictStrategy("OVERWRITE") == ConflictStrategy.OVERWRITE
        assert ConflictStrategy("FAIL") == ConflictStrategy.FAIL


class TestPolicyBackup:
    """Tests for PolicyBackup model."""

    def test_creation(self) -> None:
        from src.models.firewall_policy import PolicyBackup

        backup = PolicyBackup(
            exported_at="2026-03-17T00:00:00Z",
            source_site="default",
            policy_count=0,
            policies=[],
        )

        assert backup.version == "1.0"
        assert backup.exported_at == "2026-03-17T00:00:00Z"
        assert backup.source_site == "default"
        assert backup.policy_count == 0
        assert backup.policies == []

    def test_serialization(self) -> None:
        from src.models.firewall_policy import PolicyBackup

        backup = PolicyBackup(
            exported_at="2026-03-17T00:00:00Z",
            source_site="default",
            policy_count=1,
            policies=[{"name": "test"}],
        )

        data = backup.model_dump()
        assert data["version"] == "1.0"
        assert data["exported_at"] == "2026-03-17T00:00:00Z"
        assert data["source_site"] == "default"
        assert data["policy_count"] == 1
        assert data["policies"] == [{"name": "test"}]


# ---------------------------------------------------------------------------
# Backup tool tests
# ---------------------------------------------------------------------------


class TestBackupFirewallPolicies:
    """Tests for backup_firewall_policies tool."""

    def test_backup_success(self, firewall_client: AsyncMock, raw_policies: list[dict]) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        result = run(backup_firewall_policies("default"))

        assert result["source_site"] == "default"
        assert result["policy_count"] == 2
        assert len(result["policies"]) == 2
        assert result["version"] == "1.0"

    def test_backup_strips_server_fields(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        result = run(backup_firewall_policies("default"))

        stripped_fields = {
            "_id",
            "site_id",
            "create_time",
            "update_time",
            "origin_id",
            "origin_type",
        }
        for policy in result["policies"]:
            for field in stripped_fields:
                assert field not in policy, f"Field '{field}' should be stripped"

    def test_backup_excludes_system_policies(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        result = run(backup_firewall_policies("default"))

        names = [p["name"] for p in result["policies"]]
        assert "System Default" not in names
        assert result["policy_count"] == 2

    def test_backup_includes_system_policies(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        result = run(backup_firewall_policies("default", include_system=True))

        assert result["policy_count"] == 3
        names = [p["name"] for p in result["policies"]]
        assert "System Default" in names

    def test_backup_empty_site(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = []

        result = run(backup_firewall_policies("default"))

        assert result["policy_count"] == 0
        assert result["policies"] == []

    def test_backup_with_output_file(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            result = run(backup_firewall_policies("default", output_file=tmp_path))

            assert result["output_file"] == tmp_path
            with open(tmp_path) as f:
                saved = json.load(f)
            assert saved["policy_count"] == 2
            assert len(saved["policies"]) == 2
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_backup_cloud_api_rejected(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(NotImplementedError):
            run(backup_firewall_policies("default"))

    def test_backup_file_io_error(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import backup_firewall_policies

        firewall_client.get.return_value = raw_policies

        with pytest.raises(ValueError, match="Failed to write"):
            run(backup_firewall_policies("default", output_file="/nonexistent/dir/file.json"))


# ---------------------------------------------------------------------------
# Restore tool tests
# ---------------------------------------------------------------------------


class TestRestoreFirewallPolicies:
    """Tests for restore_firewall_policies tool."""

    def test_restore_success_create_all(
        self, firewall_client: AsyncMock, raw_policies: list[dict]
    ) -> None:
        from src.tools.firewall_policy_backup import (
            backup_firewall_policies,
            restore_firewall_policies,
        )

        # First backup to get clean policies
        firewall_client.get.return_value = raw_policies
        backup = run(backup_firewall_policies("default"))

        # Restore: no existing policies
        firewall_client.get.return_value = []
        firewall_client.post.return_value = {"status": "ok"}

        result = run(
            restore_firewall_policies(
                site_id="default",
                policies=backup["policies"],
                confirm=True,
            )
        )

        assert result["created"] == 2
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["total_processed"] == 2
        assert firewall_client.post.call_count == 2

    def test_restore_dry_run(self, firewall_client: AsyncMock, raw_policies: list[dict]) -> None:
        from src.tools.firewall_policy_backup import (
            backup_firewall_policies,
            restore_firewall_policies,
        )

        firewall_client.get.return_value = raw_policies
        backup = run(backup_firewall_policies("default"))

        result = run(
            restore_firewall_policies(
                site_id="default",
                policies=backup["policies"],
                dry_run=True,
            )
        )

        assert result["dry_run"] is True
        assert result["total_processed"] == 2
        firewall_client.post.assert_not_called()
        firewall_client.put.assert_not_called()

    def test_restore_missing_confirm(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        with pytest.raises(ValidationError, match="requires confirmation"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    policies=[{"name": "test"}],
                    confirm=False,
                )
            )

    def test_restore_conflict_skip(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        incoming = [
            {"name": "Existing Policy", "action": "BLOCK"},
            {"name": "New Policy", "action": "ALLOW"},
        ]

        # Existing policies on site
        firewall_client.get.return_value = [
            {"_id": "ex-1", "name": "Existing Policy", "action": "BLOCK"},
        ]
        firewall_client.post.return_value = {"status": "ok"}

        result = run(
            restore_firewall_policies(
                site_id="default",
                policies=incoming,
                conflict_strategy="SKIP",
                confirm=True,
            )
        )

        assert result["skipped"] == 1
        assert result["created"] == 1
        assert firewall_client.post.call_count == 1

    def test_restore_conflict_overwrite(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        incoming = [
            {"name": "Existing Policy", "action": "BLOCK"},
            {"name": "New Policy", "action": "ALLOW"},
        ]

        firewall_client.get.return_value = [
            {"_id": "ex-1", "name": "Existing Policy", "action": "ALLOW"},
        ]
        firewall_client.post.return_value = {"status": "ok"}
        firewall_client.put.return_value = {"status": "ok"}

        result = run(
            restore_firewall_policies(
                site_id="default",
                policies=incoming,
                conflict_strategy="OVERWRITE",
                confirm=True,
            )
        )

        assert result["updated"] == 1
        assert result["created"] == 1
        assert firewall_client.put.call_count == 1
        assert firewall_client.post.call_count == 1

    def test_restore_conflict_fail(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        incoming = [
            {"name": "Existing Policy", "action": "BLOCK"},
        ]

        firewall_client.get.return_value = [
            {"_id": "ex-1", "name": "Existing Policy", "action": "ALLOW"},
        ]

        with pytest.raises(ValueError, match="already exists"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    policies=incoming,
                    conflict_strategy="FAIL",
                    confirm=True,
                )
            )

    def test_restore_from_file(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        backup_data = {
            "version": "1.0",
            "exported_at": "2026-03-17T00:00:00Z",
            "source_site": "default",
            "policy_count": 1,
            "policies": [{"name": "From File", "action": "BLOCK"}],
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(backup_data, f)
            tmp_path = f.name

        try:
            firewall_client.get.return_value = []
            firewall_client.post.return_value = {"status": "ok"}

            result = run(
                restore_firewall_policies(
                    site_id="default",
                    input_file=tmp_path,
                    confirm=True,
                )
            )

            assert result["created"] == 1
            assert result["total_processed"] == 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_restore_no_input_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        with pytest.raises(ValueError, match="Exactly one of"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    confirm=True,
                )
            )

    def test_restore_both_inputs_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        with pytest.raises(ValueError, match="Exactly one of"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    policies=[{"name": "test"}],
                    input_file="/some/file.json",
                    confirm=True,
                )
            )

    def test_restore_invalid_conflict_strategy(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        with pytest.raises(ValueError, match="Invalid conflict_strategy"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    policies=[{"name": "test"}],
                    conflict_strategy="MERGE",
                    confirm=True,
                )
            )

    def test_restore_cloud_api_rejected(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        firewall_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(NotImplementedError):
            run(
                restore_firewall_policies(
                    site_id="default",
                    policies=[{"name": "test"}],
                    confirm=True,
                )
            )

    def test_restore_cross_site_warning(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        incoming = [
            {
                "name": "Cross Site Policy",
                "action": "BLOCK",
                "source": {"zone_id": "zone-a", "matching_target": "ANY"},
                "destination": {"zone_id": "zone-b", "matching_target": "ANY"},
            },
        ]

        backup_data = {
            "version": "1.0",
            "exported_at": "2026-03-17T00:00:00Z",
            "source_site": "other-site",
            "policy_count": 1,
            "policies": incoming,
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(backup_data, f)
            tmp_path = f.name

        try:
            firewall_client.get.return_value = []
            firewall_client.post.return_value = {"status": "ok"}

            result = run(
                restore_firewall_policies(
                    site_id="default",
                    input_file=tmp_path,
                    confirm=True,
                )
            )

            assert "warning" in result
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_restore_invalid_backup_format(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        bad_data = {"version": "1.0", "source_site": "default"}

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(bad_data, f)
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid backup"):
                run(
                    restore_firewall_policies(
                        site_id="default",
                        input_file=tmp_path,
                        confirm=True,
                    )
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_restore_invalid_backup_missing_version(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        bad_data = {"policies": []}

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(bad_data, f)
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid backup"):
                run(
                    restore_firewall_policies(
                        site_id="default",
                        input_file=tmp_path,
                        confirm=True,
                    )
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_restore_file_io_error(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policy_backup import restore_firewall_policies

        with pytest.raises(ValueError, match="Failed to read"):
            run(
                restore_firewall_policies(
                    site_id="default",
                    input_file="/nonexistent/backup.json",
                    confirm=True,
                )
            )
