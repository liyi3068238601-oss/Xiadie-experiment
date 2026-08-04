from __future__ import annotations

import itertools

import pytest

from app import task_run_contract as contract


def test_cyr2c_error_specs_present() -> None:
    for code in (
        "task_source_ref_unknown",
        "task_source_ref_invalid",
        "task_source_invalidated",
        "task_plan_locked_node_modified",
    ):
        assert code in contract.ERROR_SPECS
        assert contract.ERROR_SPECS[code].retry == "modify_then_retry"


RUN_STATES = (
    "draft", "planning", "awaiting_approval", "ready", "running",
    "paused", "recovery_required", "failed", "completed", "cancelled",
)
RUN_COMMANDS = ("replace_plan", "approve", "start", "pause", "resume", "replan", "cancel")
NODE_STATES = ("pending", "ready", "running", "blocked", "succeeded", "failed", "skipped", "cancelled")
NODE_COMMANDS = ("start", "succeed", "fail", "skip")


RUN_APPLY = {
    "replace_plan": {"draft", "planning", "paused", "recovery_required", "failed"},
    "approve": {"awaiting_approval"},
    "start": {"ready"},
    "pause": {"running"},
    "resume": {"paused", "recovery_required"},
    "replan": set(RUN_STATES) - {"planning", "completed", "cancelled"},
    "cancel": set(RUN_STATES) - {"completed", "cancelled"},
}
RUN_IDEMPOTENT = {
    "replace_plan": {"ready", "awaiting_approval"},
    "approve": set(),
    "start": {"running"},
    "pause": {"paused"},
    "resume": {"running"},
    "replan": {"planning"},
    "cancel": {"cancelled"},
}
RUN_TARGETS = {
    "replace_plan": None,
    "approve": "ready",
    "start": "running",
    "pause": "paused",
    "resume": "running",
    "replan": "planning",
    "cancel": "cancelled",
}


@pytest.mark.parametrize("command,status", tuple(itertools.product(RUN_COMMANDS, RUN_STATES)))
def test_run_matrix_has_one_stable_decision(command: str, status: str):
    decision = contract.decide_run(contract.RunCommandContext(
        command=command,
        status=status,
        revision=7,
        expected_revision=7,
        plan_version=3,
        requires_approval=status == "awaiting_approval",
        approved_plan_version=None,
        plan_matches=command == "replace_plan" and status in RUN_IDEMPOTENT[command],
        has_started=False,
    ))

    expected = (
        "apply" if status in RUN_APPLY[command]
        else "idempotent" if status in RUN_IDEMPOTENT[command]
        else "reject"
    )
    assert decision.outcome == expected
    if expected != "reject" and command != "replace_plan":
        assert decision.target_status == RUN_TARGETS[command]
    if expected == "reject":
        assert decision.code
        assert decision.message
        assert decision.retry in contract.RETRY_VALUES
        assert decision.instruction is None
    elif expected == "apply":
        assert decision.instruction
        assert decision.code is None
        assert decision.retry is None
    else:
        assert decision.instruction is None
        assert decision.code is None
        assert decision.retry is None


@pytest.mark.parametrize("status", RUN_STATES)
def test_approve_replay_is_bound_only_to_current_plan_version(status: str):
    decision = contract.decide_run(contract.RunCommandContext(
        command="approve",
        status=status,
        revision=9,
        expected_revision=2,
        plan_version=4,
        requires_approval=True,
        approved_plan_version=4,
    ))
    assert decision.outcome == "idempotent"
    assert decision.target_status == "ready"

    changed = contract.decide_run(contract.RunCommandContext(
        command="approve",
        status=status,
        revision=9,
        expected_revision=2,
        plan_version=5,
        requires_approval=True,
        approved_plan_version=4,
    ))
    assert changed.outcome == "reject"
    assert changed.code == "task_run_revision_conflict"


@pytest.mark.parametrize("command,status", tuple(itertools.product(RUN_COMMANDS, RUN_STATES)))
def test_non_replay_run_command_checks_revision_before_state(command: str, status: str):
    decision = contract.decide_run(contract.RunCommandContext(
        command=command,
        status=status,
        revision=8,
        expected_revision=7,
        plan_version=2,
        requires_approval=False,
        approved_plan_version=None,
        plan_matches=False,
        has_started=True,
    ))
    replay = (
        (command == "start" and status == "running")
        or (command == "pause" and status == "paused")
        or (command == "resume" and status == "running")
        or (command == "replan" and status == "planning")
        or (command == "cancel" and status == "cancelled")
    )
    if replay:
        assert decision.outcome == "idempotent"
    else:
        assert decision.outcome == "reject"
        assert decision.code == "task_run_revision_conflict"
        assert decision.retry == "refresh_then_user_retry"


def test_plan_replay_and_content_conflict_are_distinct():
    common = dict(
        command="replace_plan", status="ready", revision=3, expected_revision=3,
        plan_version=1, requires_approval=False, approved_plan_version=None, has_started=False,
    )
    exact = contract.decide_run(contract.RunCommandContext(**common, plan_matches=True))
    assert exact.outcome == "idempotent"

    different = contract.decide_run(contract.RunCommandContext(**common, plan_matches=False))
    assert different.outcome == "reject"
    assert different.code == "task_plan_content_conflict"
    assert different.retry == "modify_then_retry"


def test_start_fails_closed_when_current_plan_approval_is_missing():
    decision = contract.decide_run(contract.RunCommandContext(
        command="start", status="ready", revision=4, expected_revision=4,
        plan_version=2, requires_approval=True, approved_plan_version=1,
    ))
    assert decision.outcome == "reject"
    assert decision.code == "task_plan_approval_required"
    assert decision.retry == "not_retryable"

    approved = contract.decide_run(contract.RunCommandContext(
        command="start", status="ready", revision=4, expected_revision=4,
        plan_version=2, requires_approval=True, approved_plan_version=2,
    ))
    assert approved.outcome == "apply"
    assert approved.instruction == "start_run"


NODE_APPLY = {
    "start": {"ready"},
    "succeed": {"running"},
    "fail": {"running"},
    "skip": {"ready", "blocked"},
}
NODE_TARGETS = {
    "start": "running",
    "succeed": "succeeded",
    "fail": "failed",
    "skip": "skipped",
}


@pytest.mark.parametrize("command,status", tuple(itertools.product(NODE_COMMANDS, NODE_STATES)))
def test_node_matrix_has_one_stable_decision(command: str, status: str):
    target = NODE_TARGETS[command]
    decision = contract.decide_node(contract.NodeCommandContext(
        command=command,
        run_status="running",
        node_status=status,
        revision=5,
        expected_revision=5,
        evidence_matches=status == target,
    ))
    expected = (
        "apply" if status in NODE_APPLY[command]
        else "idempotent" if status == target
        else "reject"
    )
    assert decision.outcome == expected
    if expected != "reject":
        assert decision.target_status == target
    if expected == "reject":
        assert decision.code == "task_node_transition_invalid"
        assert decision.retry in contract.RETRY_VALUES


@pytest.mark.parametrize("command", ("succeed", "fail", "skip"))
def test_terminal_node_evidence_must_match_exactly(command: str):
    target = NODE_TARGETS[command]
    exact = contract.decide_node(contract.NodeCommandContext(
        command=command, run_status="completed", node_status=target,
        revision=12, expected_revision=4, evidence_matches=True,
    ))
    assert exact.outcome == "idempotent"

    stale_different = contract.decide_node(contract.NodeCommandContext(
        command=command, run_status="completed", node_status=target,
        revision=12, expected_revision=4, evidence_matches=False,
    ))
    assert stale_different.code == "task_run_revision_conflict"

    fresh_different = contract.decide_node(contract.NodeCommandContext(
        command=command, run_status="completed", node_status=target,
        revision=12, expected_revision=12, evidence_matches=False,
    ))
    assert fresh_different.code == "task_node_evidence_conflict"
    assert fresh_different.retry == "modify_then_retry"


def test_exact_node_replay_precedes_run_running_requirement():
    replay = contract.decide_node(contract.NodeCommandContext(
        command="succeed", run_status="completed", node_status="succeeded",
        revision=10, expected_revision=7, evidence_matches=True,
    ))
    assert replay.outcome == "idempotent"

    non_replay = contract.decide_node(contract.NodeCommandContext(
        command="start", run_status="completed", node_status="ready",
        revision=10, expected_revision=10,
    ))
    assert non_replay.outcome == "reject"
    assert non_replay.code == "task_run_transition_invalid"
    assert non_replay.retry == "not_retryable"


@pytest.mark.parametrize("run_status", RUN_STATES)
def test_artifact_links_are_append_only_in_every_run_state(run_status: str):
    requested = contract.ArtifactLink("artifact-1", "node-1", "报告")
    apply = contract.decide_artifact(contract.ArtifactCommandContext(
        run_status=run_status, revision=6, expected_revision=6,
        requested=requested, existing=None,
    ))
    assert apply.outcome == "apply"
    assert apply.instruction == "link_artifact"
    assert apply.target_status is None

    replay = contract.decide_artifact(contract.ArtifactCommandContext(
        run_status=run_status, revision=6, expected_revision=1,
        requested=requested, existing=requested,
    ))
    assert replay.outcome == "idempotent"

    conflict = contract.decide_artifact(contract.ArtifactCommandContext(
        run_status=run_status, revision=6, expected_revision=6,
        requested=requested,
        existing=contract.ArtifactLink("artifact-1", None, "其他"),
    ))
    assert conflict.outcome == "reject"
    assert conflict.code == "task_artifact_link_conflict"
    assert conflict.retry == "modify_then_retry"


def test_all_error_specs_are_static_and_complete():
    assert contract.RETRY_VALUES == frozenset({
        "refresh_then_user_retry", "modify_then_retry", "not_retryable",
    })
    for code, spec in contract.ERROR_SPECS.items():
        assert code.startswith("task_")
        assert spec.message.strip() == spec.message
        assert 0 < len(spec.message) <= 80
        assert spec.retry in contract.RETRY_VALUES
