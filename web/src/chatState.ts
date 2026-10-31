// How the chat view turns stream events into what's on screen. Kept as plain functions,
// separate from React, so the rules are easy to read and test.

import type { ChatEvent, GuardrailFlag } from "./api";

export interface ToolStep {
  id: string;
  name: string;
  done: boolean;
  isError: boolean;
}

export interface AssistantTurn {
  role: "assistant";
  text: string;
  tools: ToolStep[];
  retracted: string[] | null; // reasons, when a check replaced the streamed text
  flags: GuardrailFlag[];
  stop: string | null;
  meta: { model: string; promptVersion: string; costUsd: number; latencyMs: number } | null;
  transcriptId: string | null;
  error: string | null;
}

export interface UserTurn {
  role: "user";
  text: string;
}

export type Turn = UserTurn | AssistantTurn;

export function emptyAssistantTurn(): AssistantTurn {
  return {
    role: "assistant",
    text: "",
    tools: [],
    retracted: null,
    flags: [],
    stop: null,
    meta: null,
    transcriptId: null,
    error: null,
  };
}

// Return the assistant turn after one event. Never mutates the input.
export function applyEvent(turn: AssistantTurn, event: ChatEvent): AssistantTurn {
  switch (event.type) {
    case "text":
      return { ...turn, text: turn.text + event.text };
    case "tool_call":
      return {
        ...turn,
        tools: [...turn.tools, { id: event.id, name: event.name, done: false, isError: false }],
      };
    case "tool_result":
      return {
        ...turn,
        tools: turn.tools.map((t) =>
          t.id === event.id ? { ...t, done: true, isError: event.is_error } : t,
        ),
      };
    case "retract":
      // A final check rejected the streamed reply: show the replacement instead.
      return { ...turn, text: event.replacement, retracted: event.reason };
    case "done":
      return { ...turn, stop: event.stop };
    case "transcript":
      return {
        ...turn,
        flags: event.guardrails,
        transcriptId: event.transcript_id,
        meta: {
          model: event.model,
          promptVersion: event.prompt_version,
          costUsd: event.cost_usd,
          latencyMs: event.latency_ms,
        },
      };
    case "error":
      return { ...turn, error: event.message };
  }
}

// A plain-language label for a guardrail decision shown as a badge.
export function flagLabel(flag: GuardrailFlag): string {
  const where =
    flag.stage === "input" ? "your message" : flag.stage === "tool_result" ? "tool data" : "reply";
  if (flag.action === "redact") return `PII redacted from ${where}`;
  if (flag.action === "block")
    return flag.stage === "output"
      ? `Sentence removed by ${flag.name} check`
      : `Blocked by ${flag.name} check`;
  if (flag.action === "rewrite") return `Injected text removed from ${where}`;
  if (flag.action === "retract") return `Reply replaced by ${flag.name} check`;
  return `${flag.name}: ${flag.action}`;
}

export const TOOL_LABELS: Record<string, string> = {
  get_credit_profile: "Reading credit profile",
  get_score_history: "Reading score history",
  get_utilization: "Checking utilization",
  simulate_payoff: "Simulating a payoff",
  explain_factor: "Looking up a factor",
};
