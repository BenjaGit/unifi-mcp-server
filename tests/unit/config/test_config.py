"""Unit tests for src/config/config.py Settings class."""

import pytest

from src.config.config import APIType, Settings


class TestAPITypeEnum:
    """Tests for APIType enumeration."""

    def test_cloud_v1_value(self):
        assert APIType.CLOUD_V1.value == "cloud-v1"

    def test_cloud_ea_value(self):
        assert APIType.CLOUD_EA.value == "cloud-ea"

    def test_local_value(self):
        assert APIType.LOCAL.value == "local"

    def test_cloud_alias_removed(self):
        assert not hasattr(APIType, "CLOUD")


class TestSettingsValidateApiType:
    """Tests for Settings.validate_api_type validator."""

    def test_validate_api_type_from_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        assert settings.api_type == APIType.CLOUD_EA

    def test_validate_api_type_uppercase(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "CLOUD-V1")
        settings = Settings()
        assert settings.api_type == APIType.CLOUD_V1

    def test_validate_api_type_local(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "LOCAL")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        settings = Settings()
        assert settings.api_type == APIType.LOCAL

    def test_validate_api_type_already_enum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        assert isinstance(settings.api_type, APIType)

    def test_validate_api_type_legacy_cloud_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud")
        with pytest.raises(ValueError):
            Settings()


class TestSettingsValidatePort:
    """Tests for Settings.validate_port validator."""

    def test_validate_port_valid(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "8443")
        settings = Settings()
        assert settings.local_port == 8443

    def test_validate_port_min_boundary(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "1")
        settings = Settings()
        assert settings.local_port == 1

    def test_validate_port_max_boundary(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "65535")
        settings = Settings()
        assert settings.local_port == 65535

    def test_validate_port_zero_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "0")
        with pytest.raises(ValueError) as exc_info:
            Settings()
        assert "Port must be between 1 and 65535" in str(exc_info.value)

    def test_validate_port_too_high_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "65536")
        with pytest.raises(ValueError) as exc_info:
            Settings()
        assert "Port must be between 1 and 65535" in str(exc_info.value)


class TestSettingsLocalConfiguration:
    """Tests for Settings.validate_local_configuration validator."""

    def test_local_without_host_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.delenv("UNIFI_LOCAL_HOST", raising=False)
        with pytest.raises(ValueError) as exc_info:
            Settings()
        assert "local_host is required" in str(exc_info.value)

    def test_local_with_host_succeeds(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        settings = Settings()
        assert settings.local_host == "192.168.2.1"

    def test_cloud_without_host_succeeds(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        monkeypatch.delenv("UNIFI_LOCAL_HOST", raising=False)
        settings = Settings()
        assert settings.local_host is None


class TestSettingsBaseUrl:
    """Tests for Settings.base_url property."""

    def test_base_url_cloud_ea(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        assert settings.base_url == "https://api.ui.com"

    def test_base_url_cloud_v1(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-v1")
        settings = Settings()
        assert settings.base_url == "https://api.ui.com"

    def test_base_url_local(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "443")
        settings = Settings()
        assert settings.base_url == "https://192.168.2.1:443"

    def test_base_url_local_custom_port(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_LOCAL_PORT", "8443")
        settings = Settings()
        assert settings.base_url == "https://10.0.0.1:8443"


class TestSettingsVerifySsl:
    """Tests for Settings.verify_ssl property."""

    def test_verify_ssl_cloud_always_true(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        assert settings.verify_ssl is True

    def test_verify_ssl_local_default_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        monkeypatch.delenv("UNIFI_LOCAL_VERIFY_SSL", raising=False)
        settings = Settings()
        assert settings.verify_ssl is False

    def test_verify_ssl_local_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        monkeypatch.setenv("UNIFI_LOCAL_VERIFY_SSL", "false")
        settings = Settings()
        assert settings.verify_ssl is False


class TestSettingsGetHeaders:
    """Tests for Settings.get_headers method."""

    def test_get_headers_includes_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "my-secret-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        headers = settings.get_headers()
        assert headers["X-API-KEY"] == "my-secret-key"

    def test_get_headers_content_type(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        headers = settings.get_headers()
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_accept(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        settings = Settings()
        headers = settings.get_headers()
        assert headers["Accept"] == "application/json"


class TestSettingsApiKeys:
    """Tests for per-API key resolution.

    Network, Site Manager, and Protect keys are independent.
    """

    def test_no_network_or_remote_key_raises(self, monkeypatch: pytest.MonkeyPatch):
        """At least one usable key must be set."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API_KEY", raising=False)
        monkeypatch.delenv("UNIFI_PROTECT_API_KEY", raising=False)
        with pytest.raises(ValueError, match="UNIFI_REMOTE_API_KEY"):
            Settings()

    def test_network_key_only_is_valid(self, monkeypatch: pytest.MonkeyPatch):
        """UNIFI_NETWORK_API_KEY alone is sufficient."""
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-key")
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API_KEY", raising=False)
        monkeypatch.delenv("UNIFI_PROTECT_API_KEY", raising=False)
        settings = Settings()
        assert settings.resolved_network_api_key == "network-key"
        assert settings.resolved_site_manager_api_key is None
        assert settings.resolved_protect_api_key is None

    def test_local_key_alias_is_valid(self, monkeypatch: pytest.MonkeyPatch):
        """UNIFI_LOCAL_API_KEY should map to the local network key."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_LOCAL_API_KEY", "local-key")
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API_KEY", raising=False)
        monkeypatch.delenv("UNIFI_REMOTE_API_KEY", raising=False)
        settings = Settings()
        assert settings.resolved_network_api_key == "local-key"

    def test_remote_key_alias_is_valid_for_cloud(self, monkeypatch: pytest.MonkeyPatch):
        """UNIFI_REMOTE_API_KEY should work for cloud modes."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.delenv("UNIFI_LOCAL_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_REMOTE_API_KEY", "remote-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-v1")
        settings = Settings()
        assert settings.resolved_network_api_key == "remote-key"
        assert settings.resolved_site_manager_api_key == "remote-key"

    def test_site_manager_enabled_auto_when_remote_key_present(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Site Manager should auto-enable when remote key is configured."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_REMOTE_API_KEY", "remote-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-v1")
        settings = Settings()
        assert settings.site_manager_enabled is True

    def test_cloud_mode_allows_remote_key_when_network_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Cloud API mode can authenticate with remote key when local key is absent."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "remote-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-v1")
        settings = Settings()
        assert settings.resolved_network_api_key == "remote-key"
        assert settings.resolved_site_manager_api_key == "remote-key"

    def test_network_and_site_manager_keys_are_independent(self, monkeypatch: pytest.MonkeyPatch):
        """Both API-specific keys work independently."""
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-key")
        monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "site-manager-key")
        settings = Settings()
        # In cloud modes, resolved_network_api_key prefers the remote key
        assert settings.resolved_network_api_key == "site-manager-key"
        assert settings.resolved_site_manager_api_key == "site-manager-key"

    def test_protect_key_is_independent(self, monkeypatch: pytest.MonkeyPatch):
        """Protect key is optional and independent from other keys."""
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-key")
        monkeypatch.setenv("UNIFI_PROTECT_API_KEY", "protect-key")
        settings = Settings()
        assert settings.resolved_network_api_key == "network-key"
        assert settings.resolved_protect_api_key == "protect-key"

    def test_local_mode_requires_network_key(self, monkeypatch: pytest.MonkeyPatch):
        """Local API mode requires local Network key even if remote key exists."""
        monkeypatch.delenv("UNIFI_NETWORK_API_KEY", raising=False)
        monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "cloud-only")
        monkeypatch.setenv("UNIFI_API_TYPE", "local")
        monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.168.2.1")
        with pytest.raises(ValueError, match="UNIFI_LOCAL_API_KEY"):
            Settings()

    def test_get_headers_uses_remote_key_in_cloud_mode(self, monkeypatch: pytest.MonkeyPatch):
        """get_headers() in cloud mode prefers the remote key."""
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-key")
        monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "site-manager-key")
        settings = Settings()
        headers = settings.get_headers()
        assert headers["X-API-KEY"] == "site-manager-key"

    def test_get_headers_with_explicit_key(self, monkeypatch: pytest.MonkeyPatch):
        """get_headers(api_key=...) uses the provided key."""
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-key")
        settings = Settings()
        headers = settings.get_headers(api_key="custom-key")
        assert headers["X-API-KEY"] == "custom-key"


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_default_log_level(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.log_level == "INFO"

    def test_default_cache_ttl(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.cache_ttl == 300

    def test_default_rate_limit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.rate_limit_requests == 100

    def test_default_site(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.default_site == "default"

    def test_api_type_accepts_valid_values(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        monkeypatch.setenv("UNIFI_API_TYPE", "cloud-ea")
        monkeypatch.delenv("UNIFI_LOCAL_HOST", raising=False)
        settings = Settings()
        assert settings.api_type == APIType.CLOUD_EA

    def test_default_cloud_api_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.cloud_api_url == "https://api.ui.com"

    def test_default_audit_log_enabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "test-key")
        settings = Settings()
        assert settings.audit_log_enabled is True
