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
    """Import worker package in a clean subprocess.

    Other tests (e.g. iteration13 media jobs) may inject a non-package
    ``sys.modules['worker']`` stub. Registry checks must not depend on
    residual in-process module state.
    """
    pytest.importorskip("celery")
    import os
    import subprocess

    api = REPO / "apps" / "api"
    worker_root = WORKER
    expected_pkg = (worker_root / "worker").resolve()
    env = os.environ.copy()
    # apps/worker first so ``import worker`` resolves to apps/worker/worker
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(worker_root),
            str(api),
            str(REPO / "packages" / "ai-gateway"),
            str(REPO / "packages" / "core"),
            env.get("PYTHONPATH", ""),
        ]
    )
    required = sorted(REQUIRED)
    script = f"""
import sys
from pathlib import Path
import worker
from worker.celery_app import celery_app
import worker.tasks  # noqa: F401

expected = Path({str(expected_pkg)!r}).resolve()
assert Path(worker.__file__).resolve() == (expected / "__init__.py").resolve(), (
    worker.__file__, expected
)
assert Path(worker.tasks.__file__).resolve() == (expected / "tasks.py").resolve(), (
    worker.tasks.__file__, expected
)
registered = set(celery_app.tasks.keys())
required = set({required!r})
missing = required - registered
assert not missing, f"not registered in Celery: {{missing}}"
for entry in (celery_app.conf.beat_schedule or {{}}).values():
    assert entry["task"] in registered, entry["task"]
print("REGISTRY_OK", sorted(required & registered))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "celery registry subprocess failed\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    assert "REGISTRY_OK" in proc.stdout
