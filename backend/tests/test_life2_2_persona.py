from __future__ import annotations

import hashlib
import json

import pytest

from app import context_budget, persona, persona_v2


def _provider() -> dict[str, object]:
    return {
        "id": "deepseek", "base_url": "https://api.deepseek.com",
        "execution_location": "remote",
    }


def test_candidate_is_deterministic_bounded_and_keeps_core_identity() -> None:
    first, manifest, hashes = persona_v2.compile_candidate(mode="companionship")
    second, _, second_hashes = persona_v2.compile_candidate(mode="companionship")
    work, _, _ = persona_v2.compile_candidate(mode="focused_work")

    assert first == second
    assert hashes == second_hashes
    assert manifest["profile_version"] == "persona-profile-v2.2"
    assert "你是遐蝶本人" in first
    assert "《如我所书》" in first
    assert "曾是奥赫玛的入殓师" in first
    assert "你是遐蝶本人" in work
    assert "先解决任务" in work
    assert context_budget.estimate_tokens(first) <= persona_v2.PERSONA_TOKEN_LIMIT
    assert context_budget.estimate_tokens(work) <= persona_v2.PERSONA_TOKEN_LIMIT
    assert len(first) < len(persona.PERSONA_PROMPT)
    assert len(work) < len(persona.PERSONA_PROMPT)
    assert "温柔、悲悯、安静、克制" in persona.OBSERVER_PERSONA_SUMMARY
    assert "不默认是开拓者" in persona.OBSERVER_PERSONA_SUMMARY


def test_unknown_mode_and_style_are_rejected_at_request_boundary() -> None:
    with pytest.raises(persona_v2.PersonaResourceError, match="persona_mode_invalid"):
        persona_v2.compile_for_request(
            legacy_prompt=persona.PERSONA_PROMPT, mode="auto", style=None,
            provider=_provider(), model="deepseek-v4-flash", rollout_mode="shadow",
        )
    with pytest.raises(persona_v2.PersonaResourceError, match="persona_style_invalid"):
        persona_v2.compile_for_request(
            legacy_prompt=persona.PERSONA_PROMPT, mode="companionship",
            style={"poetic_level": "always"}, provider=_provider(),
            model="deepseek-v4-flash", rollout_mode="shadow",
        )


def test_legacy_rollout_and_mode_inputs_do_not_disable_single_agent_v23() -> None:
    shadow = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode="companionship", style=None,
        provider=_provider(), model="deepseek-v4-flash", rollout_mode="shadow",
    )
    active = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode="focused_work", style=None,
        provider=_provider(), model="deepseek-v4-flash", rollout_mode="active",
    )
    assert shadow.prompt == active.prompt
    assert shadow.selected_profile == "v2.3"
    assert active.selected_profile == "v2.3"
    assert shadow.mode == active.mode == "adaptive"
    assert shadow.selected_v2 and active.selected_v2
    assert not shadow.certified and not active.certified
    assert "不存在需要宣布或切换的“聊天模式”“工作模式”" in shadow.prompt


def test_frozen_v22_certificate_is_still_bound_to_model_mode_and_hash(tmp_path, monkeypatch) -> None:
    candidate, manifest, _ = persona_v2.compile_candidate(mode="focused_work")
    compiled_hash = hashlib.sha256(candidate.encode()).hexdigest()
    fingerprint = persona_v2.model_fingerprint(_provider(), "deepseek-v4-flash")
    certification = tmp_path / "certifications.json"
    certification.write_text(json.dumps({
        "protocol_version": "persona-certifications-v1",
        "certifications": [{
            "model_fingerprint": fingerprint,
            "profile_version": manifest["profile_version"],
            "compiler_version": manifest["compiler_version"],
            "compiled_hashes": {"focused_work": compiled_hash},
            "sampling_profile": {"temperature": 0.0},
            "output_guard_protocol": "persona-natural-dialogue-guard-v2",
            "status": "certified",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(persona_v2, "CERTIFICATIONS_PATH", certification)

    assert persona_v2.is_certified(
        fingerprint, manifest["profile_version"], manifest["compiler_version"],
        "focused_work", compiled_hash,
    )
    assert not persona_v2.is_certified(
        fingerprint, manifest["profile_version"], manifest["compiler_version"],
        "companionship", compiled_hash,
    )


def test_checked_in_v22_certificate_matches_guarded_evidence() -> None:
    payload = json.loads(persona_v2.CERTIFICATIONS_PATH.read_text(encoding="utf-8"))
    certificate = payload["certifications"][0]
    assert certificate["status"] == "certified"
    assert certificate["profile_version"] == "persona-profile-v2.2"
    assert certificate["evaluation_protocol"] == "persona-evaluation-v1.4"
    assert certificate["output_guard_protocol"] == "persona-natural-dialogue-guard-v2"
    assert len(certificate["fixture_sha256"]) == 64
    for mode in persona_v2.MODES:
        compiled, manifest, _ = persona_v2.compile_candidate(mode=mode)
        assert manifest["profile_version"] == certificate["profile_version"]
        assert hashlib.sha256(compiled.encode()).hexdigest() == certificate["compiled_hashes"][mode]
    artifact = persona_v2.PROFILE_DIR.parents[3] / "docs" / "reports" / "life2-persona-v2.2-certified-deepseek-v4-flash.json"
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == certificate["evaluation_artifact_sha256"]
    evidence = json.loads(artifact.read_text(encoding="utf-8"))
    assert all(run["summary"]["hard_pass_count"] == 150 for run in evidence["runs"])


def test_all_profile_corruption_falls_back_without_exposing_prompt(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "profiles"
    broken.mkdir()
    (broken / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken)
    monkeypatch.setattr(persona_v2, "PROFILE_DIR", broken)
    monkeypatch.setattr(persona_v2, "MANIFEST_PATH", broken / "manifest.json")

    result = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode="companionship", style=None,
        provider=_provider(), model="deepseek-v4-flash", rollout_mode="active",
    )
    meta = result.public_meta()
    assert result.prompt == persona_v2.EMERGENCY_PERSONA
    assert result.selected_profile == "emergency"
    assert result.profile_version == persona_v2.EMERGENCY_PROFILE_VERSION
    assert result.fallback_reason == "persona_all_profiles_invalid"
    assert "prompt" not in json.dumps(meta).casefold()
