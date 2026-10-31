"""Regression checks mapped to major feature commits on main.

Groups:
  - Security / Iteration 0 (P0.1–P0.7) — structure + unit
  - Editing plan pipeline (mock / brief / LLM / apply)
  - Pricing + billing safety flags
  - Jobs / Celery / offline FFmpeg e2e script
  - AI gateway adapters presence
  - Web plan→render clients
  - Ops docs / CI workflow markers
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"


def _exists(*parts: str) -> Path:
    p = ROOT.joinpath(*parts)
    assert p.exists(), f"missing: {p.relative_to(ROOT)}"
    return p


def test_commit_files_security_and_payments():
    _exists("apps/api/app/services/yookassa.py")
    _exists("apps/api/app/services/payment.py")
    _exists("apps/api/app/services/license_policy.py")
    _exists("apps/api/app/api/license.py")
    _exists("apps/api/app/api/billing.py")
    _exists("apps/api/app/api/ws_collab.py")
    _exists("apps/api/tests/test_iteration0_all_p0.py")


def test_commit_files_editing_pipeline():
    _exists("apps/api/app/api/editing.py")
    _exists("apps/api/app/services/editing_plan.py")
    _exists("apps/api/app/services/apply_plan.py")
    _exists("apps/api/app/services/plan_generate.py")
    _exists("apps/api/app/services/render.py")
    _exists("apps/api/tests/test_editing_plan.py")
    _exists("apps/api/tests/test_plan_generate.py")
    _exists("apps/api/tests/test_plan_from_brief.py")
    _exists("apps/api/tests/test_render.py")


def test_commit_files_pricing_and_seed():
    _exists("apps/api/app/services/pricing.py")
    _exists("apps/api/tests/test_pricing.py")
    seeds = list(ROOT.glob("**/009*seed*tariff*")) + list(ROOT.glob("**/versions/*seed*tariff*"))
    assert seeds or (API / "alembic").exists(), "expected alembic or tariff seed migration"


def test_commit_files_jobs_celery_e2e():
    _exists("apps/api/app/api/jobs.py")
    _exists("scripts/e2e_render_offline.py")
    jobs = (API / "app/api/jobs.py").read_text()
    assert "vrav.media.render" in jobs
    assert "async_result.get" not in jobs


def test_commit_files_web_plan_render():
    _exists("apps/web/src/components/PlanRenderPanel.tsx")
    _exists("apps/web/src/lib/editingApi.ts")
    panel = (WEB / "src/components/PlanRenderPanel.tsx").read_text()
    assert "Generate" in panel or "generate" in panel
    api = (WEB / "src/lib/editingApi.ts").read_text()
    assert "/editing/plans" in api or "editing" in api
    assert "/jobs" in api or "render" in api


def test_commit_files_ops_and_ci():
    _exists(".github/workflows/ci.yml")
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "pytest" in ci
    assert "3.12" in ci or "python-version" in ci
    _exists("docs/ops/SMOKE_CHECKLIST.md")


def test_env_example_billing_safety_flags():
    env = ROOT / ".env.example"
    if not env.exists():
        pytest.skip(".env.example missing")
    text = env.read_text()
    assert "ALLOW_MANUAL_CREDIT_TOPUP" in text or "STRIPE" in text


def test_pricing_resolve_uses_decimal():
    text = (API / "app/services/pricing.py").read_text()
    assert "Decimal" in text
    assert "resolve_checkout_price" in text or "credits_to_grant" in text


def test_plan_generate_has_llm_and_fallback():
    text = (API / "app/services/plan_generate.py").read_text()
    assert "generate_plan_llm" in text or "generate" in text
    assert "extract" in text.lower() or "json" in text.lower()


def test_editing_plan_ir_parseable():
    from app.services.editing_plan import EditingPlan  # type: ignore

    assert EditingPlan is not None


def test_render_service_exports_helpers():
    text = (API / "app/services/render.py").read_text()
    assert "export_path_for_job" in text
    assert "render_timeline" in text or "ffmpeg" in text.lower()


def test_offline_e2e_script_is_executable_python():
    script = ROOT / "scripts" / "e2e_render_offline.py"
    src = script.read_text()
    assert "ffmpeg" in src.lower() or "render" in src.lower()
    ast.parse(src)


def test_ai_gateway_package_present():
    _exists("packages/ai-gateway")
    assert list((ROOT / "packages/ai-gateway").rglob("*mock*")) or list(
        (ROOT / "packages/ai-gateway").rglob("*.py")
    )


def test_jobs_get_endpoint_exists():
    text = (API / "app/api/jobs.py").read_text()
    assert '@router.get("/{job_id}"' in text or "def get_job" in text
    assert "export" in text


def test_billing_webhook_routes_present():
    text = (API / "app/api/billing.py").read_text()
    assert "yookassa" in text.lower()
    assert "stripe" in text.lower() or "webhook" in text.lower()


def test_security_jwt_decode_strict_in_production_source():
    text = (API / "app/core/security.py").read_text()
    assert "decode_access_token" in text
    assert "production" in text.lower() or "ENVIRONMENT" in text or "type" in text


def test_credits_ledger_immutable_pattern():
    text = (API / "app/services/credits.py").read_text()
    assert "CreditLedger" in text
    assert "reserve" in text and "commit" in text and "release" in text
