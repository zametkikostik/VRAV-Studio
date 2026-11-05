"""Celery task registration / presence for worker.tasks."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WORKER = REPO / "apps" / "worker"
TASKS_PY = WORKER / "worker" / "tasks.py"
CELERY_APP_PY = WORKER / "worker" / "celery_app.py"

REQUIRED = {
    "vrav.credits.release_stale",
    "vrav.media.analyze",
    "vrav.media.transcribe",
    "vrav.media.probe",
    "vrav.media.render",
    "vrav.ping",
    "vrav.gdpr.purge",
}


def _task_names_from_source(path: Path) -> set[str]:
    text = path.read_text()
    names = set(re.findall(r'@celery_app\.task\(\s*name\s*=\s*"([^"]+)"', text))
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if (
                        kw.arg == "name"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        names.add(kw.value.value)
    except SyntaxError:
        pass
    return names


def test_tasks_source_defines_required_names():
    names = _task_names_from_source(TASKS_PY)
    missing = REQUIRED - names
    assert not missing, f"missing task definitions in tasks.py: {missing}"


def test_credits_release_stale_implementation_present():
    text = TASKS_PY.read_text()
    assert "def credits_release_stale" in text
    assert "release_stale_reservations" in text
    assert "CREDIT_RESERVATION_TTL_SECONDS" in text


def test_beat_schedule_references_registered_names():
    beat = CELERY_APP_PY.read_text()
    assert "vrav.credits.release_stale" in beat
    names = _task_names_from_source(TASKS_PY)
    assert "vrav.credits.release_stale" in names


def test_celery_registry_when_celery_installed():
    pytest.importorskip("celery")
    if str(WORKER) not in sys.path:
        sys.path.insert(0, str(WORKER))
    api = REPO / "apps" / "api"
    if str(api) not in sys.path:
        sys.path.insert(0, str(api))
    from worker.celery_app import celery_app
    import worker.tasks  # noqa: F401

    registered = set(celery_app.tasks.keys())
    missing = REQUIRED - registered
    assert not missing, f"not registered in Celery: {missing}"
    for entry in (celery_app.conf.beat_schedule or {}).values():
        assert entry["task"] in registered
