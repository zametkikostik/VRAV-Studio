"""Iteration 5 Part 2: AI agent orchestrator."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.ai_agent import AgentError, generate_video_from_prompt
from app.services.rag_search import deterministic_embed

PID = "11111111-1111-1111-1111-111111111111"
ORG = "22222222-2222-2222-2222-222222222222"
A1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
A2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _assets():
    return [
        {
            "id": A1,
            "type": "video",
            "filename": "beach.mp4",
            "storage_key": f"{ORG}/{PID}/beach.mp4",
            "embedding": deterministic_embed("beach sunset ocean"),
        },
        {
            "id": A2,
            "type": "video",
            "filename": "city.mp4",
            "storage_key": f"{ORG}/{PID}/city.mp4",
            "embedding": deterministic_embed("city traffic night"),
        },
    ]


@pytest.mark.asyncio
async def test_agent_compiles_and_queues_celery(tmp_path):
    sent = {}

    def fake_celery(name, kwargs=None, **kw):
        sent["name"] = name
        sent["kwargs"] = kwargs or {}
        return SimpleNamespace(id="celery-task-1")

    storage = tmp_path / "storage"
    storage.mkdir()
    for a in _assets():
        p = storage / a["storage_key"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake")

    paths = {a["id"]: storage / a["storage_key"] for a in _assets()}

    out = await generate_video_from_prompt(
        project_id=PID,
        organization_id=ORG,
        prompt="beach sunset montage",
        assets=_assets(),
        asset_paths=paths,
        storage_root=storage,
        model="mock/default",
        celery_send=fake_celery,
        job_id="33333333-3333-3333-3333-333333333333",
    )

    assert out["status"] == "queued"
    assert out["celery_task_id"] == "celery-task-1"
    assert sent["name"] == "vrav.media.render"
    assert len(sent["kwargs"]["clips"]) >= 1
    assert out["timeline"] is not None
    assert out["compiled_argv"][0][0] == "ffmpeg"
    assert A1 in out["selected_asset_ids"]


@pytest.mark.asyncio
async def test_agent_rejects_empty_prompt():
    with pytest.raises(AgentError, match="prompt"):
        await generate_video_from_prompt(
            project_id=PID,
            organization_id=ORG,
            prompt="  ",
            assets=_assets(),
            asset_paths={},
            storage_root="/tmp",
            celery_send=lambda *a, **k: SimpleNamespace(id="x"),
        )


@pytest.mark.asyncio
async def test_agent_with_mock_llm_chat_fn(tmp_path):
    storage = tmp_path / "s"
    storage.mkdir()
    assets = _assets()
    for a in assets:
        p = storage / a["storage_key"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    paths = {a["id"]: storage / a["storage_key"] for a in assets}

    async def chat_fn(system, user, model):
        return (
            '{"version":"1.0","project_id":"%s","source_asset_ids":["%s"],'
            '"clips":[{"asset_id":"%s","track_type":"video","duration_ms":1500,'
            '"timeline_start_ms":0,"source_in_ms":0}],'
            '"output":{"width":640,"height":360,"fps":24}}'
        ) % (PID, A1, A1)

    sent = {}

    def celery_send(name, kwargs=None, **kw):
        sent["kwargs"] = kwargs
        return SimpleNamespace(id="t2")

    out = await generate_video_from_prompt(
        project_id=PID,
        organization_id=ORG,
        prompt="use beach only",
        assets=assets,
        asset_paths=paths,
        storage_root=storage,
        model="xai/grok",
        chat_fn=chat_fn,
        celery_send=celery_send,
    )
    assert out["plan_source"] == "llm"
    assert out["timeline"]["clips"][0]["duration_ms"] == 1500
    assert sent["kwargs"]["width"] == 640


def test_api_and_schema_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "app/services/ai_agent.py").exists()
    assert (root / "app/api/ai_agent.py").exists()
    assert (root / "app/schemas/ai_agent.py").exists()
    assert "ai_agent_router" in (root / "app/main.py").read_text()
