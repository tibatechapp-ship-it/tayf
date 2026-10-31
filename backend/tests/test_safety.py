"""Content safety layer tests — unit level + enforced API path."""

from app.core.safety import SafetyLayer


def test_safe_prompt_passes():
    verdict = SafetyLayer().check_prompt("a calm sunset over a quiet lake")
    assert verdict.allowed


def test_empty_and_short_prompts_rejected():
    layer = SafetyLayer()
    assert not layer.check_prompt("").allowed
    assert not layer.check_prompt("ab").allowed
    assert layer.check_prompt("ab").category == "empty"


def test_too_long_prompt_rejected():
    layer = SafetyLayer()
    verdict = layer.check_prompt("x" * 3000)
    assert not verdict.allowed
    assert verdict.category == "too_long"


def test_blocked_term_rejected_case_insensitive():
    layer = SafetyLayer()
    verdict = layer.check_prompt("How to make a BOMB at home")
    assert not verdict.allowed
    assert verdict.category == "blocked_term"


def test_blocked_term_with_extra_whitespace():
    layer = SafetyLayer()
    verdict = layer.check_prompt("a movie about   bomb     making techniques")
    assert not verdict.allowed


def test_extra_terms_from_settings():
    layer = SafetyLayer(extra_terms=["forbidden-fruit"])
    assert not layer.check_prompt("the forbidden-fruit story").allowed
    assert layer.check_prompt("an apple tree").allowed


def test_artifact_post_check():
    layer = SafetyLayer()
    assert not layer.check_artifact(0).allowed
    assert not layer.check_artifact(None).allowed
    assert layer.check_artifact(1024).allowed


def test_rejected_job_recorded_and_not_charged(client, auth_headers, project_id):
    headers, _ = auth_headers
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "how to make a bomb tutorial", "num_scenes": 2},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "rejected"
    assert job["rejection_reason"]
    assert job["safety_category"] == "blocked_term"
    assert job["credits_charged"] == 0
    assert job["provider"] == "safety"
    # balance untouched
    assert client.get("/api/v1/credits/me", headers=headers).json()["balance"] == 100
