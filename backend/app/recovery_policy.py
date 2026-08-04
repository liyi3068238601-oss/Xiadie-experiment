"""CYR.2C recovery protocol: pure risk/allowed-action matrix (no I/O)."""
from __future__ import annotations

from typing import Literal

RecoveryClass = Literal["side_effect_free", "idempotent", "side_effectful"]
RETRY_LIMIT = 3


def decide_recovery(recovery_class: str | None, *, has_terminal_evidence: bool,
                    retries_used: int) -> dict:
    """Return authoritative recovery advice for one node/run.

    fail closed: unknown class or missing terminal ToolRun evidence only
    allows replanning.
    """
    if not has_terminal_evidence or recovery_class not in {
        "side_effect_free", "idempotent", "side_effectful",
    }:
        return {
            "risk": "none",
            "allowed": {"continue": False, "retry": False, "replan": True},
            "reasons": {
                "continue": "没有可用的工具终态证据。",
                "retry": "没有可用的工具终态证据。",
                "replan": "建议重新规划后再执行。",
            },
        }
    if recovery_class == "side_effect_free":
        return {
            "risk": "low",
            "allowed": {"continue": True, "retry": True, "replan": True},
            "reasons": {
                "continue": "最后一次工具操作无副作用，可安全继续。",
                "retry": "无副作用，可安全重试。",
                "replan": "可重新规划。",
            },
        }
    if recovery_class == "idempotent":
        retry_allowed = int(retries_used or 0) < RETRY_LIMIT
        return {
            "risk": "mid",
            "allowed": {"continue": True, "retry": retry_allowed, "replan": True},
            "reasons": {
                "continue": "幂等操作可继续，但需确认输入未变化。",
                "retry": (f"重试安全；剩余 {max(0, RETRY_LIMIT - int(retries_used or 0))} 次。"
                          if retry_allowed else "已达到重试上限（3 次）。"),
                "replan": "可重新规划。",
            },
        }
    return {
        "risk": "high",
        "allowed": {"continue": True, "retry": False, "replan": True},
        "reasons": {
            "continue": "有副作用操作，继续前需要确认。",
            "retry": "有副作用操作不可盲目重放。",
            "replan": "建议重新规划。",
        },
    }
