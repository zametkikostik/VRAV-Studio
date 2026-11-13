from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    plan_tier: str | None
    owner_user_id: str

    model_config = {"from_attributes": True}


class OrganizationMemberOut(BaseModel):
    id: str
    organization_id: str
    user_id: str
    role: str

    model_config = {"from_attributes": True}


class OrganizationMemberCreate(BaseModel):
    """POST /organizations/{org_id}/members body."""

    user_id: str = Field(min_length=36, max_length=36)
    role: str = Field(min_length=1, max_length=50)


class OrganizationMemberRoleUpdate(BaseModel):
    """PATCH /organizations/{org_id}/members/{member_id} body."""

    role: str = Field(min_length=1, max_length=50)


class OwnershipTransferRequest(BaseModel):
    """POST /organizations/{org_id}/transfer-ownership body."""

    target_user_id: str = Field(min_length=36, max_length=36)


class OwnershipTransferResult(BaseModel):
    organization_id: str
    previous_owner_user_id: str
    new_owner_user_id: str
    previous_owner_new_role: str
