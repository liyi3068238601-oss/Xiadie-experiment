export const PLAN_CARD_STATES: string[];
export function planCardState(state: string): string;
export function proposalToDraftNodes(
  nodes: Array<{
    client_id: string;
    title: string;
    depends_on?: string[];
    completion_criteria?: string;
    input_refs?: Array<{ source_kind: string; source_id: string }>;
    user_locked?: boolean;
    locked_reason?: "edit" | "explicit" | null;
    recovery_class?: string | null;
  }>,
): Array<{
  client_id: string;
  title: string;
  depends_on: string[];
  completion_criteria: string;
  input_refs: Array<{ source_kind: string; source_id: string }>;
  user_locked: boolean;
  locked_reason: "edit" | "explicit" | null;
  recovery_class: string | null;
}>;
export function lockUiState(node: {
  user_locked?: boolean;
  locked_reason?: "edit" | "explicit" | null;
}): { label: string; locked: boolean };
