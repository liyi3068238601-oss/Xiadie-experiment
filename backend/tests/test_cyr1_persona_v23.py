from __future__ import annotations

import json

from app import context_budget, persona, persona_v2


def _provider() -> dict[str, object]:
    return {
        "id": "deepseek", "base_url": "https://api.deepseek.com",
        "execution_location": "remote",
    }


def test_v23_is_deterministic_bounded_and_single_agent() -> None:
    first, manifest, hashes = persona_v2.compile_profile(profile="v2.3")
    second, second_manifest, second_hashes = persona_v2.compile_profile(profile="v2.3")
    assert first == second
    assert manifest == second_manifest
    assert hashes == second_hashes
    assert manifest["profile_version"] == "persona-profile-v2.3"
    assert manifest["behavior_policy"] == "adaptive-single-agent-v1"
    assert context_budget.estimate_tokens(first) <= persona_v2.PERSONA_TOKEN_LIMIT
    assert "你就是遐蝶本人" in first
    assert "不存在需要宣布或切换的“聊天模式”“工作模式”" in first
    assert "WorldBook 只是按需召回的遐蝶特殊知识库" in first
    assert "不主动把“AI”“语言模型”或“通用助手”当作角色身份" in first
    assert "如今你存在于《如我所书》中" not in first


def test_v23_is_selected_without_model_certificate_or_rollout_gate() -> None:
    result = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode=None, style=None,
        provider=_provider(), model="uncertified-model", rollout_mode="off",
    )
    assert result.selected_v2 is True
    assert result.certified is False
    assert result.selected_profile == "v2.3"
    assert result.mode == "adaptive"
    assert result.rollout_mode == "active"
    assert result.behavior_policy == "adaptive-single-agent-v1"
    assert result.prompt != persona.PERSONA_PROMPT
    meta = result.public_meta()
    assert meta["persona_selected_profile"] == "v2.3"
    assert meta["persona_behavior_policy"] == "adaptive-single-agent-v1"
    assert meta["persona_model_quality_status"] == "unverified"
    assert all("prompt" not in key.casefold() for key in meta)
    assert result.prompt not in json.dumps(meta, ensure_ascii=False)


def test_legacy_client_modes_compile_the_same_v23_prompt() -> None:
    chat = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode="companionship", style=None,
        provider=_provider(), model="same-model",
    )
    work = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode="focused_work", style=None,
        provider=_provider(), model="same-model",
    )
    assert chat.prompt == work.prompt
    assert chat.compiled_hash == work.compiled_hash
    assert chat.mode == work.mode == "adaptive"


def test_v23_corruption_falls_back_to_immutable_v22(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "v2_3"
    broken.mkdir()
    (broken / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken)
    result = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode=None, style=None,
        provider=_provider(), model="same-model",
    )
    expected, _, _ = persona_v2.compile_profile(
        profile="v2.2", legacy_mode="companionship",
    )
    assert result.prompt == expected
    assert result.selected_profile == "v2.2"
    assert result.fallback_reason == "persona_v23_resource_invalid"
    assert result.behavior_policy == "legacy-companionship-fallback-v1"


def test_unknown_internal_profile_fails_safe_to_v23() -> None:
    result = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode=None, style=None,
        provider=_provider(), model="same-model", profile="v9.9",
    )
    assert result.selected_profile == "v2.3"
    assert result.requested_profile == "v9.9"
    assert result.fallback_reason == "persona_profile_invalid"


def test_startup_self_check_reports_healthy_resources_without_bodies() -> None:
    status = persona_v2.startup_self_check(remember=False)
    assert status["status"] == "healthy"
    assert status["requested_profile"] == "v2.3"
    assert status["selector_status"] == "valid"
    assert status["selected_profile"] == "v2.3"
    assert status["protocol_version"] == "persona-startup-check-v1"
    assert status["emergency"]["available"] is True
    assert status["emergency"]["tokens"] > 0
    assert all(item["failures"] == [] for item in status["profiles"])
    payload = json.dumps(status, ensure_ascii=False)
    assert "你是遐蝶" not in payload


def test_startup_self_check_names_missing_resource_and_uses_v22(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "v2_3"
    broken.mkdir()
    manifest = json.loads(persona_v2.V2_3_DIR.joinpath("manifest.json").read_text(encoding="utf-8"))
    for key, spec in manifest["files"].items():
        if key != "behavior":
            source = persona_v2.V2_3_DIR / spec["path"]
            broken.joinpath(spec["path"]).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    broken.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken)

    status = persona_v2.startup_self_check(remember=False)
    assert status["status"] == "degraded"
    assert status["selected_profile"] == "v2.2"
    failures = status["profiles"][0]["failures"]
    assert failures == [{
        "code": "persona_resource_missing", "profile": "v2.3", "resource": "behavior",
    }]


def test_manifest_cannot_escape_profile_directory(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "v2_3"
    broken.mkdir()
    manifest = json.loads(persona_v2.V2_3_DIR.joinpath("manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["core"]["path"] = "../outside.md"
    broken.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken)

    report = persona_v2.inspect_profile("v2.3")
    assert {
        "code": "persona_resource_path_invalid", "profile": "v2.3", "resource": "core",
    } in report["failures"]


def test_startup_self_check_reports_hash_mismatch_by_resource(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "v2_3"
    broken.mkdir()
    manifest = json.loads(persona_v2.V2_3_DIR.joinpath("manifest.json").read_text(encoding="utf-8"))
    for spec in manifest["files"].values():
        source = persona_v2.V2_3_DIR / spec["path"]
        broken.joinpath(spec["path"]).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    broken.joinpath("core.md").write_text("tampered", encoding="utf-8")
    broken.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken)

    report = persona_v2.inspect_profile("v2.3")
    assert report["failures"] == [{
        "code": "persona_hash_mismatch", "profile": "v2.3", "resource": "core",
    }]


def test_all_resource_failure_uses_builtin_emergency_persona(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "profiles"
    broken.mkdir()
    monkeypatch.setattr(persona_v2, "V2_3_DIR", broken / "v2_3")
    monkeypatch.setattr(persona_v2, "PROFILE_DIR", broken / "v2_2")
    monkeypatch.setattr(persona_v2, "MANIFEST_PATH", broken / "v2_2" / "manifest.json")
    result = persona_v2.compile_for_request(
        legacy_prompt="must-not-be-used", mode=None, style=None,
        provider=_provider(), model="new-model",
    )
    assert result.prompt == persona_v2.EMERGENCY_PERSONA
    assert result.selected_profile == "emergency"
    assert result.behavior_policy == persona_v2.EMERGENCY_BEHAVIOR_POLICY
    assert result.output_guard_enabled is True
    assert "must-not-be-used" not in result.prompt


def test_model_quality_is_metadata_not_runtime_gate() -> None:
    assert persona_v2.model_quality_status(_provider(), "brand-new-model") == "unverified"
    result = persona_v2.compile_for_request(
        legacy_prompt=persona.PERSONA_PROMPT, mode=None, style=None,
        provider=_provider(), model="brand-new-model",
    )
    assert result.selected_profile == "v2.3"
    assert result.certified is False
