from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    status: str
    created_by: str

    model_config = {"from_attributes": True}


class SceneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    order_index: int = 0
    metadata: dict | None = None


class SceneOut(BaseModel):
    id: str
    project_id: str
    name: str
    order_index: int
    metadata: dict | None = None

    model_config = {"from_attributes": True}


class AssetCreate(BaseModel):
    type: str = Field(pattern=r"^(image|video|audio|model|other)$")
    filename: str | None = None
    mime_type: str | None = None
    scene_id: str | None = None
    metadata: dict | None = None


class AssetOut(BaseModel):
    id: str
    project_id: str
    scene_id: str | None
    type: str
    storage_key: str
    filename: str | None
    mime_type: str | None
    size_bytes: int | None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    organization_id: str
    project_id: str | None
    type: str
    status: str
    error: str | None
    created_at: str | None = None

    model_config = {"from_attributes": True}
