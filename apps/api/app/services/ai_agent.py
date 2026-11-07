"""Prompt → RAG → TimelineDefinition → FFmpeg compile → Celery render."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.services.editing_plan import plan_from_brief, plan_to_render_clips, validate_plan
from app.services.ffmpeg_compiler import compile_timeline
from app.services.plan_generate import generate_plan_llm
from app.services.rag_search import (
    RagHit,
    filter_assets_for_embedding_space,
    rank_assets_by_embedding,
)
from app.services.timeline_definition import TimelineDefinition, editing_plan_to_timeline


class AgentError(Exception):
    pass


async def generate_video_from_prompt(
    *,
    project_id: str,
    organization_id: str,
    prompt: str,
    assets: list[dict[str, Any]],
    asset_paths: dict[str, str | Path],
    storage_root: str | Path,
    top_k: int = 10,
    model: str = "mock/default",
    chat_fn: Callable[..., Awaitable[str]] | None = None,
    celery_send: Callable[..., Any] | None = None,
    job_id: str | None = None,
    embedding_provider: Any | None = None,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise AgentError("prompt is required")
    if not assets:
        raise AgentError("no assets in project")

    from app.services.embeddings import (
        EmbeddingConfigError,
        EmbeddingProviderError,
        get_embedding_provider,
    )

    try:
        provider = embedding_provider or get_embedding_provider()
        query_embedding = await provider.embed(prompt)
    except EmbeddingConfigError as e:
        raise AgentError(str(e)) from e
    except EmbeddingProviderError as e:
        raise AgentError(f"embedding provider error: {e}") from e

    dims = int(getattr(provider, "dimensions", 1536))
    compatible = filter_assets_for_embedding_space(
        assets,
        provider_name=getattr(provider, "name", "") or "",
        model=getattr(provider, "model", "") or "",
        dimensions=dims,
    )
    hits: list[RagHit] = []
    if compatible:
        hits = rank_assets_by_embedding(
            query_embedding, compatible, top_k=top_k, min_score=-1.0, expected_dim=dims
        )
    allow_nonsemantic = (
        getattr(provider, "name", "") in ("mock", "deterministic", "hash", "test")
    )
    if not hits:
        if not allow_nonsemantic:
            raise AgentError(
                "index_not_ready: no compatible segment/asset embeddings for the "
                "configured embedding space; index transcripts before semantic generation"
            )
        selected = [a for a in assets if (a.get("type") or "").lower() != "audio"]
    else:
        hit_ids = {h.asset_id for h in hits}
        selected = [a for a in assets if str(a["id"]) in hit_ids]
        order = {h.asset_id: i for i, h in enumerate(hits)}
        selected.sort(key=lambda a: order.get(str(a["id"]), 999))

    if not selected:
        raise AgentError("no suitable assets after RAG")

    plan, plan_source = await generate_plan_llm(
        project_id=project_id,
        assets=selected,
        brief=prompt,
        model=model,
        chat_fn=chat_fn,
    )
    selected_ids = {str(a["id"]) for a in selected}
    plan.clips = [c for c in plan.clips if c.asset_id in selected_ids]
    if not plan.clips:
        plan = plan_from_brief(project_id, selected, prompt)
        plan_source = f"{plan_source}+brief_fallback"
    plan = validate_plan(plan.model_dump())
    timeline: TimelineDefinition = editing_plan_to_timeline(plan)

    jid = job_id or str(uuid.uuid4())
    work = Path(storage_root) / str(organization_id) / str(project_id) / "agent" / jid
    out = work / "final.mp4"
    paths = {str(k): Path(v) for k, v in asset_paths.items() if str(k) in selected_ids}
    for a in selected:
        aid = str(a["id"])
        if aid not in paths:
            sk = a.get("storage_key") or a.get("path")
            if sk:
                paths[aid] = Path(storage_root) / str(sk) if not Path(str(sk)).is_absolute() else Path(str(sk))
    compiled = compile_timeline(timeline, paths, work, out)

    celery_clips = plan_to_render_clips(plan)
    id_to_key = {str(a["id"]): a.get("storage_key") for a in assets}
    worker_clips = []
    for c in celery_clips:
        aid = str(c["asset_id"])
        key = id_to_key.get(aid)
        if not key:
            continue
        worker_clips.append(
            {
                "storage_key": key,
                "duration_ms": c.get("duration_ms"),
                "source_in_ms": int(c.get("source_in_ms") or 0),
            }
        )
    if not worker_clips:
        raise AgentError("no renderable clips")

    root = Path(storage_root)
    rel_key = str(out.relative_to(root)) if out.is_relative_to(root) else str(out)
    task_id = None
    status = "queued"
    render_kwargs = {
        "clips": worker_clips,
        "output_key": rel_key,
        "storage_root": str(storage_root),
        "width": timeline.output.width,
        "height": timeline.output.height,
        "fps": float(timeline.output.fps),
    }
    if celery_send is None:
        try:
            from worker.celery_app import celery_app  # type: ignore

            ar = celery_app.send_task("vrav.media.render", kwargs=render_kwargs)
            task_id = ar.id
        except Exception:
            status = "compiled_only"
    else:
        ar = celery_send("vrav.media.render", kwargs=render_kwargs)
        task_id = getattr(ar, "id", None) or str(ar)

    return {
        "job_id": jid,
        "status": status,
        "celery_task_id": task_id,
        "timeline": timeline.model_dump(),
        "selected_asset_ids": [str(a["id"]) for a in selected],
        "plan_source": plan_source,
        "compiled_argv": compiled.all_argv(),
        "output_key": rel_key,
    }
