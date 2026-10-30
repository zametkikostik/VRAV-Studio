import pytest
from pydantic import ValidationError

from app.schemas.project import AssetCreate, ProjectCreate


def test_project_create():
    p = ProjectCreate(organization_id="00000000-0000-0000-0000-000000000001", name="Demo")
    assert p.name == "Demo"


def test_asset_type_validation():
    a = AssetCreate(type="video", filename="a.mp4")
    assert a.type == "video"
    with pytest.raises(ValidationError):
        AssetCreate(type="unknown")
