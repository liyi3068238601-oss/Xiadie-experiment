export const PLAN_CARD_STATES = ["loading", "pending", "editing", "failed", "cancelled"];

export const planCardState = (state) => (PLAN_CARD_STATES.includes(state) ? state : "pending");

export const proposalToDraftNodes = (nodes) =>
  (nodes || []).map((node) => ({
    client_id: node.client_id,
    title: node.title,
    depends_on: node.depends_on || [],
    completion_criteria: node.completion_criteria || "",
    input_refs: node.input_refs || [],
    user_locked: Boolean(node.user_locked),
    locked_reason: node.locked_reason || (node.user_locked ? "explicit" : null),
    recovery_class: node.recovery_class || null,
  }));

export const lockUiState = (node) => {
  if (!node?.user_locked) return { label: "", locked: false };
  return { locked: true, label: node.locked_reason === "edit" ? "已锁定 · 编辑" : "已锁定" };
};
