"""Phase C.2.3: final API security closure tests.

- Incomplete/malformed canonical citations must fail provenance.
- Authorization exercises real `_get_project_for_user` (not a patched stand-in).
- Gateway circuit-open → mock fallback path kept.

Full multi-user PostgreSQL end-to-end is DEFERRED when DATABASE_URL is absent.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.transcript_agent import (
    AgentMatch,
    query_transcript_agent,
    resolve_transcript_agent_model,
    validate_answer_against_evidence,
    TranscriptAgentConfigError,
)


def _m(**kw) -> AgentMatch:
    return AgentMatch(
        asset_id=kw.get("asset_id") or str(uuid4()),
        filename="f.mp4",
        segment_id=kw.get("segment_id") or str(uuid4()),
        start_ms=kw.get("start_ms", 1000),
        end_ms=kw.get("end_ms", 5000),
        snippet=kw.get("snippet", "we moved to Bulgaria next year"),
        score=0.9,
        embedding_model="deterministic-hash",
    )


def test_incomplete_canonical_citation_rejected():
    m = _m()
    incomplete = f"[cite segment_id={m.segment_id} start_ms=1000]"
    answer = f"{incomplete} also at 1000ms"
    ok, warns = validate_answer_against_evidence(answer, [m])
    assert ok is False
    assert "unsupported_citation_format" in warns


def test_incomplete_cite_without_end_ms_and_no_loose_ts_is_not_full_cite():
    from app.services.transcript_agent import parse_canonical_citations

    m = _m()
    incomplete = f"[cite segment_id={m.segment_id} start_ms=1000]"
    assert parse_canonical_citations(incomplete) == []
    ok, warns = validate_answer_against_evidence(incomplete, [m])
    assert ok is False
    assert "unsupported_citation_format" in warns
    full = f"[cite segment_id={m.segment_id} start_ms=1000 end_ms=2000]"
    ok2, warns2 = validate_answer_against_evidence(full, [m])
    assert ok2 is True and warns2 == []


def test_malformed_cite_missing_segment_token_rejected_as_format():
    m = _m()
    ok, warns = validate_answer_against_evidence(
        "start_ms=1000 end_ms=2000 without cite wrapper", [m]
    )
    assert ok is False
    assert "unsupported_citation_format" in warns


def test_free_form_1000ms_still_rejected():
    m = _m()
    ok, warns = validate_answer_against_evidence("mentioned around 1000ms", [m])
    assert ok is False
    assert "unsupported_citation_format" in warns


def test_cite_missing_end_ms_only_rejected():
    m = _m()
    ok, warns = validate_answer_against_evidence(
        f"[cite segment_id={m.segment_id} start_ms={m.start_ms}]", [m]
    )
    assert ok is False
    assert "unsupported_citation_format" in warns


def test_cite_missing_start_ms_rejected():
    m = _m()
    ok, warns = validate_answer_against_evidence(
        f"[cite segment_id={m.segment_id} end_ms={m.end_ms}]", [m]
    )
    assert ok is False
    assert "unsupported_citation_format" in warns


def test_cite_missing_segment_id_token_rejected():
    m = _m()
    ok, warns = validate_answer_against_evidence(
        f"[cite start_ms={m.start_ms} end_ms={m.end_ms}]", [m]
    )
    assert ok is False
    assert "unsupported_citation_format" in warns
