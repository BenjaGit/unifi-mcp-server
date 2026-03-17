"""DNS policy models."""

from pydantic import BaseModel, ConfigDict, Field


class DNSPolicy(BaseModel):
    """DNS policy model.

    Used by the Integration API (/v1/sites/{id}/dns/policies).
    UniFi DNS policies define DNS record overrides (A, CNAME, etc.)
    for local DNS resolution on the gateway.
    """

    id: str = Field(..., description="DNS policy identifier")
    type: str | None = Field(None, description="Record type (A_RECORD, CNAME, etc.)")
    enabled: bool | None = Field(None, description="Whether the policy is active")
    name: str | None = Field(None, description="Policy name or hostname")
    domain: str | None = Field(None, description="Domain name")
    value: str | None = Field(None, description="Record value (IP address, hostname)")
    ttl_seconds: int | None = Field(None, alias="ttlSeconds", description="TTL in seconds")
    priority: int | None = Field(None, description="Policy priority")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
