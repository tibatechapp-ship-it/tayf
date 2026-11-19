"""Branding and entitlement facts shared by API, pipeline, and tests.

The plan is server-owned (``users.plan``). The UI only displays it; every
watermark decision is snapshotted on the job at creation time so a later plan
change can never rewrite an already accepted job.
"""

from __future__ import annotations

from typing import Any

BRAND_AR = "المناظر"
BRAND_EN = "Al-Manazir"
WATERMARK_TEXT = "Al-Manazir"

FREE_PLAN = "free"
PRO_PLAN = "pro"
PRO_PACKAGE = "pro"
BRANDING_POLICY_VERSION = 1


def normalize_plan(plan: object) -> str:
    """Unknown or missing values stay Free — fail closed on entitlement."""
    return PRO_PLAN if plan == PRO_PLAN else FREE_PLAN


def watermark_for(plan: object) -> bool:
    """Free videos carry the watermark; Pro videos do not."""
    return normalize_plan(plan) == FREE_PLAN


def branding_snapshot(plan: object) -> dict[str, Any]:
    """Build the immutable per-job branding decision stored in ``input_params``."""
    normalized = normalize_plan(plan)
    return {
        "brand": BRAND_EN,
        "plan": normalized,
        "watermark": watermark_for(normalized),
        "policy_version": BRANDING_POLICY_VERSION,
    }


def job_branding(input_params: dict[str, Any] | None) -> dict[str, Any]:
    """Read a job snapshot; pre-Batch-2 jobs keep their legacy behavior."""
    raw = input_params.get("branding") if isinstance(input_params, dict) else None
    if not isinstance(raw, dict) or raw.get("policy_version") != BRANDING_POLICY_VERSION:
        return {
            "legacy": True,
            "brand": BRAND_EN,
            "plan": "legacy",
            "watermark": False,
            "policy_version": 0,
        }
    return {
        "legacy": False,
        "brand": str(raw.get("brand") or BRAND_EN),
        "plan": normalize_plan(raw.get("plan")),
        "watermark": bool(raw.get("watermark")),
        "policy_version": BRANDING_POLICY_VERSION,
    }
