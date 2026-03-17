"""Configuration management for UniFi MCP Server using Pydantic Settings."""

from enum import Enum
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIType(str, Enum):
    """API connection type enumeration."""

    CLOUD_V1 = "cloud-v1"  # Official stable v1 API
    CLOUD_EA = "cloud-ea"  # Early Access API
    LOCAL = "local"  # Direct gateway access


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys.
    # Project terminology:
    # - LOCAL key  -> UNIFI_LOCAL_API_KEY (alias: UNIFI_NETWORK_API_KEY)
    # - REMOTE key -> UNIFI_REMOTE_API_KEY (alias: UNIFI_SITE_MANAGER_API_KEY)
    #
    # Network and Site Manager use different authentication systems:
    # - LOCAL key is typically used for local gateway access
    # - REMOTE key is typically used for cloud access
    # Protect keys are generated in UniFi Protect.

    network_api_key: SecretStr | None = Field(
        default=None,
        description="API key for the Network API (generated in gateway UI)",
        validation_alias=AliasChoices("UNIFI_LOCAL_API_KEY", "UNIFI_NETWORK_API_KEY"),
    )

    site_manager_api_key: SecretStr | None = Field(
        default=None,
        description="API key for the Site Manager API (generated at account.ui.com/api)",
        validation_alias=AliasChoices("UNIFI_REMOTE_API_KEY", "UNIFI_SITE_MANAGER_API_KEY"),
    )

    protect_api_key: SecretStr | None = Field(
        default=None,
        description="API key for the Protect API",
        validation_alias="UNIFI_PROTECT_API_KEY",
    )

    api_type: APIType = Field(
        default=APIType.CLOUD_EA,
        description="API connection type: 'cloud-v1' (stable), 'cloud-ea' (early access), or 'local' (gateway)",
        validation_alias="UNIFI_API_TYPE",
    )

    # Cloud API Configuration
    cloud_api_url: str = Field(
        default="https://api.ui.com",
        description="UniFi Cloud API base URL",
        validation_alias="UNIFI_CLOUD_API_URL",
    )

    # Local API Configuration
    local_host: str | None = Field(
        default=None,
        description="Local UniFi controller hostname/IP",
        validation_alias="UNIFI_LOCAL_HOST",
    )

    local_port: int = Field(
        default=443,
        description="Local UniFi controller port",
        validation_alias="UNIFI_LOCAL_PORT",
    )

    local_verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificates for local controller",
        validation_alias="UNIFI_LOCAL_VERIFY_SSL",
    )

    # Site Configuration
    default_site: str = Field(
        default="default",
        description="Default site ID to use",
        validation_alias="UNIFI_DEFAULT_SITE",
    )

    # Site Manager API Configuration
    site_manager_enabled: bool = Field(
        default=False,
        description="Enable Site Manager API (multi-site management)",
        validation_alias="UNIFI_SITE_MANAGER_ENABLED",
    )

    # Rate Limiting Configuration
    rate_limit_requests: int = Field(
        default=100,
        description="Maximum requests per minute (EA tier: 100, v1 tier: 10000)",
        validation_alias="UNIFI_RATE_LIMIT_REQUESTS",
    )

    rate_limit_period: int = Field(
        default=60,
        description="Rate limit period in seconds",
        validation_alias="UNIFI_RATE_LIMIT_PERIOD",
    )

    # Retry Configuration
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts for failed requests",
        validation_alias="UNIFI_MAX_RETRIES",
    )

    retry_backoff_factor: float = Field(
        default=2.0,
        description="Exponential backoff factor for retries",
        validation_alias="UNIFI_RETRY_BACKOFF_FACTOR",
    )

    # Timeout Configuration
    request_timeout: int = Field(
        default=30,
        description="Request timeout in seconds",
        validation_alias="UNIFI_REQUEST_TIMEOUT",
    )

    # Caching Configuration
    cache_enabled: bool = Field(
        default=True,
        description="Enable response caching",
        validation_alias="UNIFI_CACHE_ENABLED",
    )

    cache_ttl: int = Field(
        default=300,
        description="Cache TTL in seconds (default: 5 minutes)",
        validation_alias="UNIFI_CACHE_TTL",
    )

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
        validation_alias="LOG_LEVEL",
    )

    log_api_requests: bool = Field(
        default=True,
        description="Log all API requests",
        validation_alias="LOG_API_REQUESTS",
    )

    # Audit Logging
    audit_log_enabled: bool = Field(
        default=True,
        description="Enable audit logging for mutating operations",
        validation_alias="UNIFI_AUDIT_LOG_ENABLED",
    )

    @field_validator("api_type", mode="before")
    @classmethod
    def validate_api_type(cls, v: str) -> APIType:
        """Validate and convert API type to enum.

        Args:
            v: API type string

        Returns:
            APIType enum value
        """
        if isinstance(v, APIType):
            return v
        return APIType(v.lower())

    @field_validator("local_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range.

        Args:
            v: Port number

        Returns:
            Validated port number

        Raises:
            ValueError: If port is invalid
        """
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        """Validate required configuration.

        Returns:
            Validated settings instance

        Raises:
            ValueError: If required configuration is missing
        """
        if self.api_type == APIType.LOCAL and not self.local_host:
            raise ValueError("local_host is required when api_type is 'local'")

        # Key requirements by connection type:
        # - local: requires local Network key
        # - cloud: accepts local Network key or remote Site Manager key
        if self.api_type == APIType.LOCAL and not self.network_api_key:
            raise ValueError(
                "UNIFI_LOCAL_API_KEY (or UNIFI_NETWORK_API_KEY) must be set for local API mode"
            )

        if self.api_type in (APIType.CLOUD_V1, APIType.CLOUD_EA):
            if not self.network_api_key and not self.site_manager_api_key:
                raise ValueError(
                    "Either UNIFI_REMOTE_API_KEY (or UNIFI_SITE_MANAGER_API_KEY) "
                    "or UNIFI_LOCAL_API_KEY (or UNIFI_NETWORK_API_KEY) must be set"
                )

        # Auto-enable Site Manager features whenever a remote key is present.
        if self.site_manager_api_key:
            self.site_manager_enabled = True

        return self

    @property
    def base_url(self) -> str:
        """Get the appropriate base URL based on API type.

        Returns:
            Base URL for API requests
        """
        if self.api_type in (APIType.CLOUD_V1, APIType.CLOUD_EA):
            return self.cloud_api_url
        else:
            # Always use HTTPS for local gateways (port 443)
            # SSL verification is controlled separately via verify_ssl property
            return f"https://{self.local_host}:{self.local_port}"

    @property
    def verify_ssl(self) -> bool:
        """Get SSL verification setting based on API type.

        Returns:
            Whether to verify SSL certificates
        """
        if self.api_type in (APIType.CLOUD_V1, APIType.CLOUD_EA):
            return True
        return self.local_verify_ssl

    @property
    def resolved_network_api_key(self) -> str:
        """Get the API key for the Network API.

        In cloud modes, prefers UNIFI_REMOTE_API_KEY (cloud-scoped)
        and falls back to UNIFI_LOCAL_API_KEY.
        In local mode, uses UNIFI_LOCAL_API_KEY.
        """
        if self.api_type in (APIType.CLOUD_V1, APIType.CLOUD_EA):
            key = self.site_manager_api_key or self.network_api_key
        else:
            key = self.network_api_key
        return key.get_secret_value() if key else ""

    @property
    def resolved_site_manager_api_key(self) -> str | None:
        """Get the API key for the Site Manager API.

        Returns None if UNIFI_SITE_MANAGER_API_KEY is not set.
        """
        return self.site_manager_api_key.get_secret_value() if self.site_manager_api_key else None

    @property
    def resolved_protect_api_key(self) -> str | None:
        """Get the API key for the Protect API.

        Returns None if UNIFI_PROTECT_API_KEY is not set.
        """
        return self.protect_api_key.get_secret_value() if self.protect_api_key else None

    def get_headers(self, api_key: str | None = None) -> dict[str, str]:
        """Get HTTP headers for API requests.

        Args:
            api_key: Specific API key to use. If None, uses the network key.

        Returns:
            Dictionary of HTTP headers
        """
        key = api_key or self.resolved_network_api_key
        return {
            "X-API-KEY": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
