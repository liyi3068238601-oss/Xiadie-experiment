"""Pure TaskRun command decisions for the CYR.2B contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RunStatus = Literal[
    "draft", "planning", "awaiting_approval", "ready", "running",
    "paused", "recovery_required", "failed", "completed", "cancelled",
]
RunCommand = Literal["replace_plan", "approve", "start", "pause", "resume", "replan", "cancel"]
NodeStatus = Literal["pending", "ready", "running", "blocked", "succeeded", "failed", "skipped", "cancelled"]
NodeCommand = Literal["start", "succeed", "fail", "skip"]
Retry = Literal["refresh_then_user_retry", "modify_then_retry", "not_retryable"]
Outcome = Literal["apply", "idempotent", "reject"]

RUN_TERMINAL = frozenset({"completed", "cancelled"})
NODE_TERMINAL = frozenset({"succeeded", "failed", "skipped", "cancelled"})
RETRY_VALUES = frozenset({"refresh_then_user_retry", "modify_then_retry", "not_retryable"})


@dataclass(frozen=True)
class ErrorSpec:
    message: str
    retry: Retry


ERROR_SPECS: dict[str, ErrorSpec] = {
    "task_run_revision_conflict": ErrorSpec(
        "任务已在其他位置更新，请查看最新状态后重试。", "refresh_then_user_retry",
    ),
    "task_run_transition_invalid": ErrorSpec(
        "当前任务状态不接受这个操作。", "refresh_then_user_retry",
    ),
    "task_node_transition_invalid": ErrorSpec(
        "当前步骤状态不接受这个操作。", "refresh_then_user_retry",
    ),
    "task_plan_replace_not_allowed": ErrorSpec(
        "当前任务状态不允许替换计划。", "not_retryable",
    ),
    "task_plan_content_conflict": ErrorSpec(
        "提交的计划与当前计划不一致。", "modify_then_retry",
    ),
    "task_node_evidence_conflict": ErrorSpec(
        "提交的步骤证据与已有证据不一致。", "modify_then_retry",
    ),
    "task_artifact_link_conflict": ErrorSpec(
        "该产物已经使用不同参数关联。", "modify_then_retry",
    ),
    "task_plan_approval_required": ErrorSpec(
        "当前计划尚未获得明确批准。", "not_retryable",
    ),
    "task_plan_node_count_invalid": ErrorSpec(
        "计划步骤数量必须在允许范围内。", "modify_then_retry",
    ),
    "task_plan_node_invalid": ErrorSpec(
        "计划包含无效或重复的步骤。", "modify_then_retry",
    ),
    "task_plan_dependencies_invalid": ErrorSpec(
        "计划步骤的依赖格式无效。", "modify_then_retry",
    ),
    "task_plan_dependency_unknown": ErrorSpec(
        "计划引用了不存在的依赖步骤。", "modify_then_retry",
    ),
    "task_plan_cycle": ErrorSpec(
        "计划步骤之间不能形成循环依赖。", "modify_then_retry",
    ),
    "task_source_ref_unknown": ErrorSpec(
        "计划引用了不存在的来源。", "modify_then_retry",
    ),
    "task_source_ref_invalid": ErrorSpec(
        "计划引用了已失效的来源。", "modify_then_retry",
    ),
    "task_source_invalidated": ErrorSpec(
        "计划包含已失效的来源引用，无法开始执行。", "modify_then_retry",
    ),
    "task_plan_locked_node_modified": ErrorSpec(
        "已锁定步骤在重新生成中不能修改。", "modify_then_retry",
    ),
}


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    target_status: str | None = None
    instruction: str | None = None
    code: str | None = None
    message: str | None = None
    retry: Retry | None = None


@dataclass(frozen=True)
class RunCommandContext:
    command: RunCommand
    status: RunStatus
    revision: int
    expected_revision: int
    plan_version: int
    requires_approval: bool
    approved_plan_version: int | None
    plan_matches: bool = False
    has_started: bool = False


@dataclass(frozen=True)
class NodeCommandContext:
    command: NodeCommand
    run_status: RunStatus
    node_status: NodeStatus
    revision: int
    expected_revision: int
    evidence_matches: bool = False


@dataclass(frozen=True)
class ArtifactLink:
    artifact_id: str
    node_id: str | None
    label: str


@dataclass(frozen=True)
class ArtifactCommandContext:
    run_status: RunStatus
    revision: int
    expected_revision: int
    requested: ArtifactLink
    existing: ArtifactLink | None


def apply(instruction: str, target_status: str | None = None) -> Decision:
    return Decision("apply", target_status=target_status, instruction=instruction)


def idempotent(target_status: str | None = None) -> Decision:
    return Decision("idempotent", target_status=target_status)


def reject(code: str, *, retry: Retry | None = None) -> Decision:
    spec = ERROR_SPECS[code]
    return Decision(
        "reject", code=code, message=spec.message, retry=retry or spec.retry,
    )


def _revision_matches(revision: int, expected_revision: int) -> bool:
    return int(revision) == int(expected_revision)


def decide_run(context: RunCommandContext) -> Decision:
    command = context.command
    status = context.status

    if command == "replace_plan" and context.plan_matches and not context.has_started \
            and status in {"ready", "awaiting_approval"}:
        return idempotent(status)
    if command == "approve" and context.approved_plan_version == context.plan_version:
        return idempotent("ready")
    if command in {"start", "resume"} and status == "running":
        return idempotent("running")
    if command == "pause" and status == "paused":
        return idempotent("paused")
    if command == "replan" and status == "planning":
        return idempotent("planning")
    if command == "cancel" and status == "cancelled":
        return idempotent("cancelled")

    if not _revision_matches(context.revision, context.expected_revision):
        return reject("task_run_revision_conflict")

    if command == "replace_plan":
        if status in {"ready", "awaiting_approval"} and not context.has_started:
            return reject("task_plan_content_conflict")
        if status in {"draft", "planning", "paused", "recovery_required", "failed"}:
            return apply("replace_plan")
        return reject("task_plan_replace_not_allowed")

    if command == "approve":
        if status == "awaiting_approval":
            return apply("approve_plan", "ready")
        return _run_transition_reject(status)

    if command == "start":
        if status != "ready":
            return _run_transition_reject(status)
        if context.requires_approval and context.approved_plan_version != context.plan_version:
            return reject("task_plan_approval_required")
        return apply("start_run", "running")

    if command == "pause":
        if status == "running":
            return apply("pause_run", "paused")
        return _run_transition_reject(status)

    if command == "resume":
        if status in {"paused", "recovery_required"}:
            return apply("resume_run", "running")
        return _run_transition_reject(status)

    if command == "replan":
        if status not in RUN_TERMINAL:
            return apply("replan_run", "planning")
        return _run_transition_reject(status)

    if command == "cancel":
        if status not in RUN_TERMINAL:
            return apply("cancel_run", "cancelled")
        return _run_transition_reject(status)

    raise ValueError(f"unsupported run command: {command}")


def _run_transition_reject(status: RunStatus) -> Decision:
    retry: Retry = "not_retryable" if status in RUN_TERMINAL else "refresh_then_user_retry"
    return reject("task_run_transition_invalid", retry=retry)


def decide_node(context: NodeCommandContext) -> Decision:
    target = {
        "start": "running",
        "succeed": "succeeded",
        "fail": "failed",
        "skip": "skipped",
    }[context.command]

    if context.node_status == target and context.evidence_matches:
        return idempotent(target)

    if not _revision_matches(context.revision, context.expected_revision):
        return reject("task_run_revision_conflict")

    if context.node_status == target and target in NODE_TERMINAL:
        return reject("task_node_evidence_conflict")

    if context.run_status != "running":
        return _run_transition_reject(context.run_status)

    allowed = (
        context.command == "start" and context.node_status == "ready"
        or context.command in {"succeed", "fail"} and context.node_status == "running"
        or context.command == "skip" and context.node_status in {"ready", "blocked"}
    )
    if not allowed:
        retry: Retry = "not_retryable" if context.node_status in NODE_TERMINAL else "refresh_then_user_retry"
        return reject("task_node_transition_invalid", retry=retry)
    return apply(f"{context.command}_node", target)


def decide_artifact(context: ArtifactCommandContext) -> Decision:
    if context.existing == context.requested:
        return idempotent()
    if not _revision_matches(context.revision, context.expected_revision):
        return reject("task_run_revision_conflict")
    if context.existing is not None:
        return reject("task_artifact_link_conflict")
    return apply("link_artifact")
