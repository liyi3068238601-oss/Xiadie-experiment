"""Versioned deterministic Persona compiler for the single Xiadie agent."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from . import context_budget, db, persona_output_guard

PROFILE_ROOT = Path(__file__).with_name("persona_profiles")
V2_2_DIR = PROFILE_ROOT / "v2_2"
V2_3_DIR = PROFILE_ROOT / "v2_3"
# Compatibility constants for the frozen v2.2 certification tests and scripts.
PROFILE_DIR = V2_2_DIR
MANIFEST_PATH = V2_2_DIR / "manifest.json"
CERTIFICATIONS_PATH = V2_2_DIR / "certifications.json"

DEFAULT_PROFILE = "v2.3"
PROFILE_KEY = "assistant.persona.profile"
INSTALLED_PROFILES = frozenset({"v2.2", "v2.3"})
LEGACY_MODES = ("companionship", "focused_work")
MODES = LEGACY_MODES
BEHAVIOR_POLICY = "adaptive-single-agent-v1"
DEFAULT_STYLE = {
    "address_style": "natural",
    "detail_level": "balanced",
    "poetic_level": "balanced",
    "proactivity_level": "balanced",
}
STYLE_OPTIONS = {
    "address_style": frozenset({"natural", "ge_xia_low", "name_if_known", "none"}),
    "detail_level": frozenset({"concise", "balanced", "detailed"}),
    "poetic_level": frozenset({"low", "balanced", "high"}),
    "proactivity_level": frozenset({"reserved", "balanced", "engaged"}),
}
PERSONA_TOKEN_LIMIT = 1450


@dataclass(frozen=True)
class PersonaCompilation:
    prompt: str
    candidate_prompt: str
    profile_version: str
    compiler_version: str
    mode: str
    rollout_mode: str
    selected_v2: bool
    certified: bool
    section_hashes: Mapping[str, str]
    compiled_hash: str
    candidate_tokens: int
    fallback_reason: str | None
    requested_profile: str = DEFAULT_PROFILE
    selected_profile: str = DEFAULT_PROFILE
    behavior_policy: str = BEHAVIOR_POLICY

    def public_meta(self) -> dict[str, object]:
        return {
            "profile_version": self.profile_version,
            "compiler_version": self.compiler_version,
            # Retain old keys for body-free diagnostic readers; mode is no longer user state.
            "persona_mode": self.mode,
            "persona_rollout_mode": self.rollout_mode,
            "persona_v2_selected": self.selected_v2,
            "persona_model_quality_status": "verified" if self.certified else "unverified",
            "persona_model_certified": self.certified,
            "persona_requested_profile": self.requested_profile,
            "persona_selected_profile": self.selected_profile,
            "persona_behavior_policy": self.behavior_policy,
            "persona_section_hashes": dict(self.section_hashes),
            "persona_compiled_hash": self.compiled_hash,
            "persona_candidate_tokens": self.candidate_tokens,
            "persona_fallback_reason": self.fallback_reason,
        }


class PersonaResourceError(ValueError):
    pass


def model_fingerprint(provider: Mapping[str, object] | None, model: str) -> str:
    payload = {
        "provider_id": str((provider or {}).get("id") or "mock"),
        "base_url": str((provider or {}).get("base_url") or "").rstrip("/"),
        "model": str(model),
        "execution_location": str((provider or {}).get("execution_location") or "unknown"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def compile_for_request(
    *, legacy_prompt: str, mode: str | None, style: Mapping[str, str] | None,
    provider: Mapping[str, object] | None, model: str,
    rollout_mode: str | None = None, profile: str | None = None,
) -> PersonaCompilation:
    """Compile one adaptive Persona; legacy mode/rollout inputs are compatibility-only."""
    if mode is not None and mode not in LEGACY_MODES:
        raise PersonaResourceError("persona_mode_invalid")
    _validate_style(style)
    configured = profile or db.get_setting(PROFILE_KEY, DEFAULT_PROFILE)
    invalid_selector = configured not in INSTALLED_PROFILES
    requested_profile = configured if configured else DEFAULT_PROFILE
    selected = DEFAULT_PROFILE if invalid_selector else configured
    fallback_reason = "persona_profile_invalid" if invalid_selector else None

    if selected == "v2.3":
        try:
            prompt, manifest, hashes = compile_profile(profile="v2.3", style=style)
            return _result(
                prompt=prompt, manifest=manifest, hashes=hashes,
                requested_profile=requested_profile, selected_profile="v2.3",
                fallback_reason=fallback_reason, provider=provider, model=model,
                behavior_policy=BEHAVIOR_POLICY,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            fallback_reason = "persona_v23_resource_invalid"

    # v2.2 is an immutable operational fallback. Old client mode is deliberately
    # ignored so fallback behavior cannot reintroduce invisible per-session modes.
    try:
        prompt, manifest, hashes = compile_profile(
            profile="v2.2", style=style, legacy_mode="companionship",
        )
        return _result(
            prompt=prompt, manifest=manifest, hashes=hashes,
            requested_profile=requested_profile, selected_profile="v2.2",
            fallback_reason=fallback_reason, provider=provider, model=model,
            behavior_policy="legacy-companionship-fallback-v1",
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        digest = hashlib.sha256(legacy_prompt.encode()).hexdigest()
        return PersonaCompilation(
            prompt=legacy_prompt, candidate_prompt="", profile_version="legacy",
            compiler_version="legacy", mode="adaptive", rollout_mode="active",
            selected_v2=False, certified=False, section_hashes={}, compiled_hash=digest,
            candidate_tokens=0, fallback_reason="persona_all_profiles_invalid",
            requested_profile=requested_profile, selected_profile="legacy",
            behavior_policy="legacy-static-fallback-v1",
        )


def _result(*, prompt: str, manifest: dict, hashes: Mapping[str, str],
            requested_profile: str, selected_profile: str, fallback_reason: str | None,
            provider: Mapping[str, object] | None, model: str,
            behavior_policy: str) -> PersonaCompilation:
    compiled_hash = hashlib.sha256(prompt.encode()).hexdigest()
    certified = is_certified(
        model_fingerprint(provider, model), manifest["profile_version"],
        manifest["compiler_version"], "companionship", compiled_hash,
        profile_dir=V2_2_DIR if selected_profile == "v2.2" else V2_3_DIR,
    )
    return PersonaCompilation(
        prompt=prompt, candidate_prompt=prompt,
        profile_version=manifest["profile_version"],
        compiler_version=manifest["compiler_version"], mode="adaptive",
        rollout_mode="active", selected_v2=True, certified=certified,
        section_hashes=hashes, compiled_hash=compiled_hash,
        candidate_tokens=context_budget.estimate_tokens(prompt),
        fallback_reason=fallback_reason, requested_profile=requested_profile,
        selected_profile=selected_profile, behavior_policy=behavior_policy,
    )


def compile_profile(*, profile: str, style: Mapping[str, str] | None = None,
                    legacy_mode: str = "companionship") -> tuple[str, dict, dict[str, str]]:
    if profile not in INSTALLED_PROFILES:
        raise PersonaResourceError("persona_profile_invalid")
    _validate_style(style)
    manifest, loaded, hashes = _load_profile_resources(profile)
    style_map = json.loads(loaded["styles"])
    chosen = dict(DEFAULT_STYLE)
    if style:
        for key, value in style.items():
            if key not in DEFAULT_STYLE or value not in style_map[key]:
                raise PersonaResourceError("persona_style_invalid")
            chosen[key] = value
    style_lines = [style_map[key][chosen[key]] for key in DEFAULT_STYLE]
    behavior_key = "behavior" if profile == "v2.3" else legacy_mode
    if profile == "v2.2" and legacy_mode not in LEGACY_MODES:
        raise PersonaResourceError("persona_mode_invalid")
    parts = [
        loaded["core"], loaded[behavior_key],
        "# 用户表达偏好\n\n" + "\n".join(f"- {line}" for line in style_lines),
        loaded["output_contract"],
    ]
    prompt = "\n\n".join(parts).strip()
    if context_budget.estimate_tokens(prompt) > PERSONA_TOKEN_LIMIT:
        raise PersonaResourceError("persona_token_budget_exceeded")
    return prompt, manifest, hashes


def compile_candidate(*, mode: str, style: Mapping[str, str] | None = None) -> tuple[str, dict, dict[str, str]]:
    """Frozen v2.2 compiler entry retained for historical certification evidence."""
    return compile_profile(profile="v2.2", style=style, legacy_mode=mode)


def derive_observer_summary(*, fallback: str) -> str:
    """Derive the observer's compact anchor from the current verified Core."""
    try:
        _, loaded, _ = _load_profile_resources(DEFAULT_PROFILE)
        sections = {
            heading.strip(): body.strip()
            for heading, body in re.findall(
                r"(?ms)^# ([^\n]+)\n\n(.*?)(?=^# |\Z)", loaded["core"],
            )
        }
        personality_sentences = [
            item.strip() for item in sections["身份与人格"].split("。") if item.strip()
        ][:2]
        relationship_sentences = [
            item.strip() for item in sections["你与用户"].split("。") if item.strip()
        ][:2]
        summary = "。".join([*personality_sentences, *relationship_sentences]).strip() + "。"
        return summary if summary else fallback
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return fallback


def _validate_style(style: Mapping[str, str] | None) -> None:
    if not style:
        return
    for key, value in style.items():
        if key not in STYLE_OPTIONS or value not in STYLE_OPTIONS[key]:
            raise PersonaResourceError("persona_style_invalid")


def _load_profile_resources(profile: str) -> tuple[dict, dict[str, str], dict[str, str]]:
    profile_dir = V2_3_DIR if profile == "v2.3" else PROFILE_DIR
    manifest_path = profile_dir / "manifest.json" if profile == "v2.3" else MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]
    loaded: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for key, spec in files.items():
        raw = (profile_dir / spec["path"]).read_text(encoding="utf-8")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if digest != spec["sha256"]:
            raise PersonaResourceError(f"persona_hash_mismatch:{key}")
        loaded[key] = raw.strip()
        hashes[key] = digest
    return manifest, loaded, hashes


def is_certified(
    fingerprint: str, profile_version: str, compiler_version: str,
    mode: str, compiled_hash: str, *, profile_dir: Path | None = None,
) -> bool:
    certification_path = (profile_dir / "certifications.json") if profile_dir else CERTIFICATIONS_PATH
    try:
        payload = json.loads(certification_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return any(
        item.get("model_fingerprint") == fingerprint
        and item.get("profile_version") == profile_version
        and item.get("compiler_version") == compiler_version
        and isinstance(item.get("compiled_hashes"), dict)
        and item["compiled_hashes"].get(mode) == compiled_hash
        and item.get("sampling_profile") == {"temperature": 0.0}
        and item.get("output_guard_protocol") == persona_output_guard.PROTOCOL_VERSION
        and item.get("status") == "certified"
        for item in payload.get("certifications", []) if isinstance(item, dict)
    )
