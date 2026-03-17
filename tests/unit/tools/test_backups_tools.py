"""Tests for backups LocalProvider tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.backups as backups_module
from src.api.network_client import SiteInfo
from src.config import APIType
from src.tools.backups import (
    delete_backup,
    download_backup,
    get_backup_details,
    get_backup_schedule,
    get_backup_status,
    get_restore_status,
    list_backups,
    restore_backup,
    schedule_backups,
    trigger_backup,
    validate_backup,
)
from src.utils.exceptions import ResourceNotFoundError, ValidationError


def make_network_client(api_type: APIType = APIType.LOCAL) -> AsyncMock:
    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type, default_site="default")
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SiteInfo(name="default", uuid="uuid-default"))
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.integration_base_path = MagicMock(side_effect=lambda ep: f"/integration/v1/{ep}")
    client.post = AsyncMock()
    client.get = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    client.raw_request = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def patch_log_audit():
    with patch.object(backups_module, "log_audit", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def network_client():
    client = make_network_client()
    with patch("src.tools.backups.get_network_client", return_value=client):
        yield client


class TestTriggerBackup:
    @pytest.mark.asyncio
    async def test_success(self, network_client):
        network_client.post.return_value = {
            "data": {"url": "/data/backup/backup_20260105.unf", "id": "backup-123"}
        }

        result = await trigger_backup("default", "network", retention_days=30, confirm=True)

        assert result["status"] == "completed"
        assert result["filename"].endswith(".unf")
        network_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self):
        result = await trigger_backup(
            "default", "system", retention_days=7, confirm=True, dry_run=True
        )

        assert result["dry_run"] is True
        assert result["would_create"]["backup_type"] == "system"

    @pytest.mark.asyncio
    async def test_requires_confirm(self):
        with pytest.raises(ValidationError):
            await trigger_backup("default", "network", retention_days=30, confirm=False)

    @pytest.mark.asyncio
    async def test_invalid_type(self):
        with pytest.raises(ValidationError):
            await trigger_backup("default", "invalid", confirm=True)

    @pytest.mark.asyncio
    async def test_invalid_retention(self):
        with pytest.raises(ValidationError):
            await trigger_backup("default", "network", retention_days=0, confirm=True)


class TestListBackups:
    @pytest.mark.asyncio
    async def test_success(self, network_client):
        network_client.post.return_value = [
            {
                "id": "backup-1",
                "filename": "backup_20260101.unf",
                "size": 5000000,
                "datetime": "2026-01-01T12:00:00Z",
                "type": "NETWORK",
                "valid": True,
            },
            {
                "id": "backup-2",
                "name": "backup_20260102.unifi",
                "filesize": 100000000,
                "created": "2026-01-02T12:00:00Z",
                "valid": True,
                "cloud_backup": True,
            },
        ]

        backups = await list_backups("default")

        assert len(backups) == 2
        assert backups[0]["filename"] == "backup_20260101.unf"
        assert backups[1]["backup_type"] == "SYSTEM"

    @pytest.mark.asyncio
    async def test_empty(self, network_client):
        network_client.post.return_value = []

        result = await list_backups("default")
        assert result == []


class TestGetBackupDetails:
    @pytest.mark.asyncio
    async def test_success(self, network_client):
        network_client.post.return_value = [
            {
                "id": "backup-1",
                "filename": "backup_20260101.unf",
                "size": 5000000,
                "datetime": "2026-01-01T12:00:00Z",
                "type": "NETWORK",
                "valid": True,
                "version": "8.0.26",
            }
        ]

        result = await get_backup_details("default", "backup_20260101.unf")

        assert result["filename"] == "backup_20260101.unf"
        assert result["version"] == "8.0.26"

    @pytest.mark.asyncio
    async def test_not_found(self, network_client):
        network_client.post.return_value = []

        with pytest.raises(ResourceNotFoundError):
            await get_backup_details("default", "missing.unf")


class TestDownloadBackup:
    @pytest.mark.asyncio
    async def test_success(self, network_client, tmp_path):
        backup_content = b"UNIFI_BACKUP_CONTENT_TEST_DATA"
        network_client.raw_request.return_value = MagicMock(content=backup_content)

        output_path = tmp_path / "test_backup.unf"

        result = await download_backup("default", "backup_20260101.unf", str(output_path))

        assert result["size_bytes"] == len(backup_content)
        assert result["checksum"] is not None
        assert output_path.exists()
        assert output_path.read_bytes() == backup_content

    @pytest.mark.asyncio
    async def test_no_checksum(self, network_client, tmp_path):
        backup_content = b"BACKUP_DATA"
        network_client.raw_request.return_value = MagicMock(content=backup_content)

        output_path = tmp_path / "test_backup.unf"

        result = await download_backup(
            "default", "backup.unf", str(output_path), verify_checksum=False
        )

        assert result["checksum"] is None


class TestDeleteBackup:
    @pytest.mark.asyncio
    async def test_success(self, network_client):
        result = await delete_backup("default", "old_backup.unf", confirm=True)

        assert result["status"] == "deleted"
        assert result["backup_filename"] == "old_backup.unf"
        network_client.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, network_client):
        result = await delete_backup("default", "backup.unf", confirm=True, dry_run=True)

        assert result["dry_run"] is True
        network_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self):
        with pytest.raises(ValidationError):
            await delete_backup("default", "backup.unf", confirm=False)


class TestRestoreBackup:
    @pytest.mark.asyncio
    async def test_success_with_pre_backup(self, network_client):
        network_client.post.side_effect = [
            {"data": {"url": "/data/backup/pre_restore.unf", "id": "pre-restore"}},
            {"status": "ok"},
        ]

        result = await restore_backup(
            "default", "backup_20260101.unf", create_pre_restore_backup=True, confirm=True
        )

        assert result["status"] == "restore_initiated"
        assert result["pre_restore_backup_id"] == "pre-restore"
        assert result["can_rollback"] is True

    @pytest.mark.asyncio
    async def test_no_pre_backup(self, network_client):
        network_client.post.return_value = {"status": "ok"}

        result = await restore_backup(
            "default", "backup.unf", create_pre_restore_backup=False, confirm=True
        )

        assert result["pre_restore_backup_id"] is None
        assert result["can_rollback"] is False

    @pytest.mark.asyncio
    async def test_dry_run(self):
        result = await restore_backup(
            "default", "backup.unf", create_pre_restore_backup=True, confirm=True, dry_run=True
        )

        assert result["dry_run"] is True
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_requires_confirm(self):
        with pytest.raises(ValidationError):
            await restore_backup("default", "backup.unf", confirm=False)


class TestValidateBackup:
    @pytest.mark.asyncio
    async def test_valid_backup(self, network_client):
        network_client.post.return_value = [
            {
                "id": "backup-1",
                "filename": "valid_backup.unf",
                "size": 10000000,
                "datetime": "2026-01-01T12:00:00Z",
                "type": "NETWORK",
                "valid": True,
                "version": "8.0.26",
            }
        ]

        result = await validate_backup("default", "valid_backup.unf")

        assert result["is_valid"] is True
        assert result["errors"] == []
        assert result["backup_version"] == "8.0.26"

    @pytest.mark.asyncio
    async def test_invalid_empty_backup(self, network_client):
        network_client.post.return_value = [
            {
                "id": "backup-1",
                "filename": "empty_backup.unf",
                "size": 0,
                "datetime": "2026-01-01T12:00:00Z",
                "valid": False,
            }
        ]

        result = await validate_backup("default", "empty_backup.unf")

        assert result["is_valid"] is False
        assert any("empty" in err.lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_warnings(self, network_client):
        network_client.post.return_value = [
            {
                "id": "backup-1",
                "filename": "small_backup.unf",
                "size": 500,
                "datetime": "2026-01-01T12:00:00Z",
                "valid": True,
            }
        ]

        result = await validate_backup("default", "small_backup.unf")

        assert result["is_valid"] is True
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_not_found(self, network_client):
        network_client.post.return_value = []

        result = await validate_backup("default", "missing.unf")

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0


class TestBackupStatus:
    @pytest.mark.asyncio
    async def test_get_backup_status_success(self, network_client):
        network_client.get.return_value = {
            "status": "completed",
            "progress": 100,
            "step": "Finalizing",
            "started_at": "2026-01-24T10:00:00Z",
            "completed_at": "2026-01-24T10:02:30Z",
            "backup": {"id": "backup-123", "filename": "backup_20260124.unf"},
        }

        result = await get_backup_status("op_backup_abc123")

        assert result["status"] == "completed"
        assert result["progress_percent"] == 100
        assert result["operation_id"] == "op_backup_abc123"

    @pytest.mark.asyncio
    async def test_get_backup_status_fallback(self, network_client):
        network_client.get.side_effect = Exception("API error")

        result = await get_backup_status("op_backup_abc123")

        assert result["status"] == "completed"
        assert "not available" in result["message"]

    @pytest.mark.asyncio
    async def test_get_restore_status_not_supported(self):
        result = await get_restore_status("op_restore_xyz789")

        assert result["status"] == "not_supported"


class TestScheduleBackups:
    @pytest.mark.asyncio
    async def test_daily_success(self, network_client):
        network_client.get.return_value = [
            {"key": "super_mgmt", "_id": "super-mgmt-1", "autobackup_enabled": False}
        ]
        network_client.put.return_value = {"key": "super_mgmt", "_id": "super-mgmt-1"}

        result = await schedule_backups(
            site_id="default",
            backup_type="network",
            frequency="daily",
            time_of_day="03:00",
            retention_days=30,
            max_backups=10,
            confirm=True,
        )

        assert result["frequency"] == "daily"
        assert result["backup_type"] == "network"
        network_client.get.assert_awaited_once()
        network_client.put.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_weekly_success(self, network_client):
        network_client.get.return_value = [
            {"key": "super_mgmt", "_id": "super-mgmt-1", "autobackup_enabled": False}
        ]
        network_client.put.return_value = {"key": "super_mgmt", "_id": "super-mgmt-1"}

        result = await schedule_backups(
            site_id="default",
            backup_type="system",
            frequency="weekly",
            time_of_day="02:00",
            day_of_week=6,
            retention_days=90,
            confirm=True,
        )

        assert result["frequency"] == "weekly"
        assert result["day_of_week"] == 6

    @pytest.mark.asyncio
    async def test_dry_run(self):
        result = await schedule_backups(
            site_id="default",
            backup_type="network",
            frequency="daily",
            time_of_day="03:00",
            confirm=True,
            dry_run=True,
        )

        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_requires_confirm(self):
        with pytest.raises(ValidationError):
            await schedule_backups(
                site_id="default",
                backup_type="network",
                frequency="daily",
                time_of_day="03:00",
                confirm=False,
            )

    @pytest.mark.asyncio
    async def test_invalid_frequency(self):
        with pytest.raises(ValidationError):
            await schedule_backups(
                site_id="default",
                backup_type="network",
                frequency="hourly",
                time_of_day="03:00",
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_invalid_time(self):
        with pytest.raises(ValidationError):
            await schedule_backups(
                site_id="default",
                backup_type="network",
                frequency="daily",
                time_of_day="25:00",
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_weekly_missing_day(self):
        with pytest.raises(ValidationError):
            await schedule_backups(
                site_id="default",
                backup_type="network",
                frequency="weekly",
                time_of_day="03:00",
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_monthly_missing_day(self):
        with pytest.raises(ValidationError):
            await schedule_backups(
                site_id="default",
                backup_type="network",
                frequency="monthly",
                time_of_day="03:00",
                confirm=True,
            )


class TestGetBackupSchedule:
    @pytest.mark.asyncio
    async def test_configured(self, network_client):
        network_client.get.return_value = [
            {"key": "mgmt", "site_id": "default"},
            {
                "key": "super_mgmt",
                "autobackup_enabled": True,
                "autobackup_cron_expr": "0 3 * * *",
                "autobackup_max_files": 10,
                "autobackup_timezone": "Europe/Copenhagen",
                "backup_to_cloud_enabled": True,
            },
        ]

        result = await get_backup_schedule("default")

        assert result["configured"] is True
        assert result["cron_expr"] == "0 3 * * *"

    @pytest.mark.asyncio
    async def test_not_configured(self, network_client):
        network_client.get.return_value = []

        result = await get_backup_schedule("default")

        assert result["configured"] is False
        assert "No automated backup" in result["message"]

    @pytest.mark.asyncio
    async def test_error(self, network_client):
        network_client.get.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await get_backup_schedule("default")
