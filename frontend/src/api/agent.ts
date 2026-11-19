/** Pandu agent HTTP client: POST /api/v1/agent/pandu/ */

import { request } from "./client";
import { DocumentRequestError } from "./documents";

export type PanduReplyStatus = "ok" | "clarify" | "abstain" | "error";

export type PanduAgentReply = {
  type: "message";
  status: PanduReplyStatus;
  text: string;
  citations: unknown[];
  tool_trace: unknown[];
};

export type PanduAgentRequest = {
  message: string;
  course_id?: number;
  conversation_id?: number;
  document_ids?: number[];
};

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function reply(value: unknown): PanduAgentReply {
  if (
    !record(value) ||
    value.type !== "message" ||
    typeof value.text !== "string" ||
    !value.text.trim() ||
    !["ok", "clarify", "abstain", "error"].includes(String(value.status)) ||
    !Array.isArray(value.citations) ||
    !Array.isArray(value.tool_trace)
  ) {
    throw new Error("The server returned an invalid Pandu reply.");
  }
  return {
    type: "message",
    status: value.status as PanduReplyStatus,
    text: value.text,
    citations: value.citations,
    tool_trace: value.tool_trace,
  };
}

/** Ask Pandu through the agent loop. Returns the JSON envelope (may be status error). */
export async function askPanduAgent(
  body: PanduAgentRequest,
  token: string,
  signal: AbortSignal,
): Promise<PanduAgentReply> {
  const response = await request(
    "/agent/pandu/",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    },
    token,
  );
  const value: unknown = await response.json().catch(() => null);
  // Auth / ownership / validation never enter the agent envelope.
  if (!response.ok) throw new DocumentRequestError(response.status, value);
  return reply(value);
}
