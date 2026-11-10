import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project, Scene
from app.schemas.asset_serializers import asset_to_out
from app.schemas.transcript_agent import AgentMatchOut, AgentQueryRequest, AgentQueryResponse
from app.schemas.project import (
    AssetCreate,
    AssetOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    RagSearchHitOut,
    RagSearchRequest,
    RagSearchResponse,
    SceneCreate,
    SceneOut,
)
from app.services.storage import get_storage

router = APIRouter(tags=["projects"])


async def _get_project_for_user(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Read access: any org member with project:read (viewer+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.PROJECT_READ)


async def _get_project_for_update(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Mutating project/scene/asset metadata: project:update (editor+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.PROJECT_UPDATE)


async def _get_project_for_delete(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Soft-delete project: project:delete (admin+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.PROJECT_DELETE)


async def _get_project_for_asset_write(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    """Create/upload assets: asset:write (editor+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.ASSET_WRITE)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DbSession):
    try:
        org_id = uuid.UUID(body.organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization_id")
    from app.services.rbac import Permission, require_org_permission
    await require_org_permission(db, user.id, org_id, Permission.PROJECT_CREATE)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=body.name,
        description=body.description,
        status="draft",
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    return ProjectOut(
        id=str(project.id),
        organization_id=str(project.organization_id),
        name=project.name,
        description=project.description,
        status=project.status,
        created_by=str(project.created_by),
    )


@router.get("/organizations/{org_id}/projects", response_model=list[ProjectOut])
async def list_org_projects(org_id: uuid.UUID, user: CurrentUser, db: DbSession):
    from app.services.rbac import Permission, require_org_permission
    await require_org_permission(db, user.id, org_id, Permission.PROJECT_READ)
    result = await db.execute(
        select(Project).where(Project.organization_id == org_id, Project.deleted_at.is_(None))
    )
    projects = result.scalars().all()
    return [
        ProjectOut(
            id=str(p.id),
            organization_id=str(p.organization_id),
            name=p.name,
            description=p.description,
            status=p.status,
            created_by=str(p.created_by),
        )
        for p in projects
    ]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    project = await _get_project_for_user(db, user.id, project_id)
    return ProjectOut(
        id=str(project.id),
        organization_id=str(project.organization_id),
        name=project.name,
        description=project.description,
        status=project.status,
        created_by=str(project.created_by),
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, db: DbSession):
    project = await _get_project_for_update(db, user.id, project_id)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        project.status = body.status
    await db.flush()
    return ProjectOut(
        id=str(project.id),
        organization_id=str(project.organization_id),
        name=project.name,
        description=project.description,
        status=project.status,
        created_by=str(project.created_by),
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    project = await _get_project_for_delete(db, user.id, project_id)
    project.deleted_at = datetime.now(timezone.utc)
    await db.flush()


@router.post("/projects/{project_id}/scenes", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
async def create_scene(project_id: uuid.UUID, body: SceneCreate, user: CurrentUser, db: DbSession):
    project = await _get_project_for_update(db, user.id, project_id)
    scene = Scene(
        id=uuid.uuid4(),
        project_id=project.id,
        name=body.name,
        order_index=body.order_index,
        metadata_=body.metadata,
    )
    db.add(scene)
    await db.flush()
    return SceneOut(
        id=str(scene.id),
        project_id=str(scene.project_id),
        name=scene.name,
        order_index=scene.order_index,
        metadata=scene.metadata_,
    )


@router.get("/projects/{project_id}/scenes", response_model=list[SceneOut])
async def list_scenes(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _get_project_for_user(db, user.id, project_id)
    result = await db.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.order_index)
    )
    scenes = result.scalars().all()
    return [
        SceneOut(
            id=str(s.id),
            project_id=str(s.project_id),
            name=s.name,
            order_index=s.order_index,
            metadata=s.metadata_,
        )
        for s in scenes
    ]


@router.post("/projects/{project_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(project_id: uuid.UUID, body: AssetCreate, user: CurrentUser, db: DbSession):
    project = await _get_project_for_asset_write(db, user.id, project_id)
    scene_id = None
    if body.scene_id:
        try:
            scene_id = uuid.UUID(body.scene_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scene_id")
        scene = await db.get(Scene, scene_id)
        if scene is None or scene.project_id != project.id:
            raise HTTPException(status_code=400, detail="Scene not found in this project")
    storage = get_storage()
    key = storage.make_key(str(project.organization_id), str(project.id), body.filename)
    await storage.put(key, b"", content_type=body.mime_type)
    pending = db.info.setdefault("pending_storage_keys", [])
    pending.append(key)
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project_id,
        scene_id=scene_id,
        type=body.type,
        storage_key=key,
        filename=body.filename,
        mime_type=body.mime_type,
        size_bytes=0,
        metadata_=body.metadata,
    )
    db.add(asset)
    try:
        await db.flush()
    except Exception:
        try:
            await storage.delete(key)
        except Exception:
            pass
        raise
    return asset_to_out(asset)


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
async def list_assets(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _get_project_for_user(db, user.id, project_id)
    result = await db.execute(
        select(Asset).where(Asset.project_id == project_id, Asset.deleted_at.is_(None))
    )
    assets = result.scalars().all()
    return [asset_to_out(a) for a in assets]


@router.post(
    "/projects/{project_id}/search",
    response_model=RagSearchResponse,
)
@router.post(
    "/projects/{project_id}/rag/search",
    response_model=RagSearchResponse,
    include_in_schema=False,
)
async def search_project_assets(
    project_id: uuid.UUID,
    body: RagSearchRequest,
    user: CurrentUser,
    db: DbSession,
):
    """Semantic timestamped segment search (Phase B)."""
    from app.services.rag_search import RagError
    from app.services.embeddings import (
        EmbeddingAuthError,
        EmbeddingConfigError,
        EmbeddingProviderError,
        get_embedding_provider,
    )
    from app.services.segment_index import search_project_segments

    await _get_project_for_user(db, user.id, project_id)
    try:
        provider = get_embedding_provider()
        dims = int(getattr(provider, "dimensions", 1536))
        query_embedding = await provider.embed(body.query)

        segment_hits = await search_project_segments(
            db,
            project_id=project_id,
            query_embedding=query_embedding,
            provider_name=getattr(provider, "name", "") or "",
            model=getattr(provider, "model", "") or "",
            dimensions=dims,
            top_k=body.top_k,
        )
        if segment_hits:
            return RagSearchResponse(
                query=body.query,
                results=[
                    RagSearchHitOut(
                        asset_id=h.asset_id,
                        asset_name=h.asset_name,
                        asset_type=None,
                        score=h.score,
                        snippet=h.snippet,
                        segment_id=h.segment_id,
                        start_ms=h.start_ms,
                        end_ms=h.end_ms,
                        embedding_model=h.embedding_model,
                    )
                    for h in segment_hits
                ],
                status="ok",
                embedding_model=str(getattr(provider, "model", None) or provider.name),
            )

        return RagSearchResponse(
            query=body.query,
            results=[],
            status="index_not_ready",
            detail=(
                "No transcript-segment index for the configured embedding space. "
                "Enqueue media.index_segments after transcription."
            ),
            embedding_model=str(getattr(provider, "model", None) or provider.name),
        )
    except EmbeddingConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except EmbeddingAuthError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except EmbeddingProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except RagError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/projects/{project_id}/agent/query",
    response_model=AgentQueryResponse,
)
async def agent_query_project(
    project_id: uuid.UUID,
    body: AgentQueryRequest,
    user: CurrentUser,
    db: DbSession,
):
    """Phase C: grounded NL Q&A over timestamped transcript segments."""
    from app.services.transcript_agent import (
        TranscriptAgentValidationError,
        query_transcript_agent,
    )
    from app.services.embeddings import (
        EmbeddingAuthError,
        EmbeddingConfigError,
        EmbeddingProviderError,
    )
    from app.services.rag_search import RagError

    project = await _get_project_for_user(db, user.id, project_id)
    try:
        result = await query_transcript_agent(
            db,
            project_id=project_id,
            query=body.query,
            top_k=body.top_k,
            min_score=body.min_score,
            user_id=user.id,
            organization_id=project.organization_id,
            generate_answer=body.generate_answer,
        )
    except TranscriptAgentValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except EmbeddingConfigError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except EmbeddingAuthError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except EmbeddingProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except RagError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return AgentQueryResponse(
        query=result.query,
        status=result.status,
        grounded_answer=result.grounded_answer,
        matches=[
            AgentMatchOut(
                asset_id=m.asset_id,
                filename=m.filename,
                segment_id=m.segment_id,
                start_ms=m.start_ms,
                end_ms=m.end_ms,
                snippet=m.snippet,
                score=m.score,
                embedding_model=m.embedding_model or None,
            )
            for m in result.matches
        ],
        embedding_model=result.embedding_model,
        warnings=result.warnings,
        detail=result.detail,
    )
