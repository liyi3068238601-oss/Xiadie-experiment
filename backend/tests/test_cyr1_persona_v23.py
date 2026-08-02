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
