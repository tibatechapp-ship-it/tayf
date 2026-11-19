"""Arabic NLP normalization: deterministic helpers and proof-chain integration."""

from __future__ import annotations

import time

from app.core import arabic_nlp

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def test_has_arabic_and_code_mixing_spans() -> None:
    text = "أحمد and ٣ scenes"
    assert arabic_nlp.has_arabic(text) is True
    assert arabic_nlp.has_arabic("plain english only") is False
    spans = arabic_nlp.code_mixing_spans(text)
    assert [span["kind"] for span in spans] == ["ar", "latin", "digit", "latin"]
    assert spans[2]["text"] == "٣"


def test_normalize_arabic_preserves_diacritics_and_is_idempotent() -> None:
    raw = "أَحْـمَدْ في المقهى، العدد ٣؟"
    normalized = arabic_nlp.normalize_arabic(raw)
    assert "أ" not in normalized
    assert "ـ" not in normalized
    assert "٣" not in normalized and "3" in normalized
    assert "؟" not in normalized and "?" in normalized
    assert "َ" in normalized  # tashkeel is preserved, never invented or stripped
    assert arabic_nlp.normalize_arabic(normalized) == normalized


def test_augment_storyboard_system_keeps_json_contract() -> None:
    base = "Return JSON only."
    augmented = arabic_nlp.augment_storyboard_system(base)
    assert augmented.startswith(base)
    assert "Modern Standard Arabic" in augmented
    assert "do not translate" in augmented
    assert "tashkeel is explicitly requested" not in augmented
    with_tashkeel = arabic_nlp.augment_storyboard_system(base, tashkeel=True)
    assert "tashkeel is explicitly requested" in with_tashkeel


def test_arabic_pipeline_records_proof_and_normalizes_scenes(client, auth_headers, project_id) -> None:  # noqa: ANN001
    headers, _ = auth_headers
    prompt = "أحمد يرتب مشهداً في المقهى، ٣ لقطات سينمائية"
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": prompt, "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    deadline = time.time() + 180.0
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline and job["status"] not in TERMINAL:
        time.sleep(0.25)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "completed", job

    proof_response = client.get(f"/api/v1/jobs/{job_id}/proof", headers=headers)
    assert proof_response.status_code == 200, proof_response.text
    proof = proof_response.json()
    assert proof["chain"]["valid"] is True

    ar_events = [event for event in proof["events"] if event["stage"] == "arabic_nlp"]
    assert len(ar_events) >= 2
    assert all(event["verification"]["allowed"] for event in ar_events)
    stages = {event["verification"]["stage"] for event in ar_events}
    assert {"pre_storyboard", "post_storyboard"} <= stages

    pre = next(event for event in ar_events if event["verification"]["stage"] == "pre_storyboard")
    assert pre["outputs"]["changed"] is True
    assert any(span["kind"] == "digit" for span in pre["outputs"]["code_mix"])

    # The mock provider echoes the normalized prompt into every scene.
    scenes = job["scenes"]
    assert scenes
    assert all("أ" not in scene["description"] for scene in scenes)
    assert all("٣" not in scene["description"] for scene in scenes)
