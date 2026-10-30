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
