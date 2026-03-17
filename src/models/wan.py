"""WAN connection models."""

from pydantic import BaseModel, ConfigDict, Field


class WANConnection(BaseModel):
    """WAN connection from the Integration API (/v1/sites/{id}/wans).

    The API returns only id and name. Additional fields from the API
    response are captured via extra="allow".
    """

    id: str = Field(..., description="WAN connection identifier")
    name: str = Field(..., description="WAN connection name")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
