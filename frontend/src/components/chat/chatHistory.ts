import type { ConversationMessage, QuestionCitation, ToolTraceEntry } from "../../api/conversations";
import type { ChatCitation, ChatMessage, ChatToolUse } from "../../types/chat";

// The backend saves this reply with empty text; live and reloaded replies read the same.
export const NO_CONTEXT_TEXT = "I couldn’t find enough information in the selected references to answer that question.";

function plural(count: number, word: string) { return `${count} ${word}${count === 1 ? "" : "s"}`; }

// PDF pages and PPTX slides are real locations. A DOCX page number is an internal
// value (always 1), never shown as a page.
export function citationView(item: QuestionCitation): ChatCitation {
  // PDF/PPTX use real locations. DOCX never shows an internal page. Agent partial
  // citations often omit format — still show page when we have one.
  const location = item.source_format === "pdf" ? `Page ${item.page_number}` :
    item.source_format === "pptx" ? `Slide ${item.page_number}` :
    item.source_format === null ? `Page ${item.page_number}` : null;
  const name = item.document_name ?? "Source";
  return {
    id: `${item.chunk_id}:${item.document_id}`,
    label: !item.available ? "Source no longer available" : location ? `${name} · ${location}` : name,
    detail: item.excerpt,
    source: { documentId: item.document_id, name: item.document_name, format: item.source_format, page: item.page_number, available: item.available },
  };
}

// One entry per search that actually ran; unknown tools are skipped, not guessed at.
export function toolUses(trace: ToolTraceEntry[]): ChatToolUse[] {
  return trace.flatMap((entry, index) => {
    if (!("tool" in entry) || entry.tool !== "search_sources") return [];
    const course = entry.sources?.course_materials;
    const uploads = entry.sources?.chat_uploads;
    const summary = course && uploads ? "Searched course materials and your uploads" :
      course ? "Searched course materials" : uploads ? "Searched your uploads" : "Searched your sources";
    const details = [
      ...(course ? [`${plural(course.documents_searched, "course material")} · ${plural(course.passages_used, "passage")} used`] : []),
      ...(uploads ? [`${plural(uploads.documents_searched, "upload")} · ${plural(uploads.passages_used, "passage")} used`] : []),
    ];
    return [{ id: `${entry.tool}-${index}`, summary, details }];
  });
}

const AGENT_TOOL_LABELS: Record<string, string> = {
  ask_course_question: "Searched course materials",
  retrieve_chunks: "Searched course materials",
  answer_from_sources: "Answered from materials",
  list_materials: "Listed materials",
  list_courses: "Listed courses",
  list_tasks: "Checked tasks",
  recall_history: "Checked chat history",
  generate_notes: "Generated notes",
  generate_quiz: "Generated a quiz",
};

/** Agent loop tool_trace shape: [{ name, ok }] (or legacy status) from /agent/pandu/. */
export function agentToolUses(trace: unknown[]): ChatToolUse[] {
  return trace.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
    const row = entry as Record<string, unknown>;
    if (typeof row.name !== "string" || !row.name.trim()) return [];
    const ok = row.ok === true || row.status === "ok";
    // Failed tool calls stay out of the student-facing summary.
    if (!ok) return [];
    const label = AGENT_TOOL_LABELS[row.name] ?? `Used ${row.name}`;
    return [{ id: `${row.name}-${index}`, summary: label, details: [] }];
  });
}

/** Best-effort citations from the agent envelope (may be empty or partial). */
export function agentCitationViews(citations: unknown[]): ChatCitation[] {
  return citations.flatMap((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const row = item as Record<string, unknown>;
    // Full SCRUM-24 described citation.
    if (
      typeof row.chunk_id === "number" &&
      typeof row.document_id === "number" &&
      typeof row.page_number === "number" &&
      typeof row.excerpt === "string" &&
      typeof row.available === "boolean"
    ) {
      return [citationView(row as QuestionCitation)];
    }
    // Minimal grounded citation from tools / model.
    const documentId = typeof row.document_id === "number" ? row.document_id : null;
    const page = typeof row.page_number === "number" ? row.page_number :
      typeof row.page === "number" ? row.page : null;
    const excerpt = typeof row.excerpt === "string" ? row.excerpt :
      typeof row.text === "string" ? row.text : "";
    if (documentId === null) return [];
    const label = page !== null ? `Source · Page ${page}` : "Source";
    return [{
      id: `agent-${documentId}-${page ?? index}`,
      label,
      detail: excerpt,
      source: {
        documentId,
        name: typeof row.document_name === "string" ? row.document_name : null,
        format: null,
        page: page ?? 1,
        available: true,
      },
    }];
  });
}

export function toChatMessage(item: ConversationMessage): ChatMessage {
  if (item.role === "user") {
    return {
      id: `message-${item.id}`, serverId: item.id, role: "user", text: item.content,
      ...(item.status === "FAILED" ? { state: "failed" as const } : item.status === "PENDING" ? { state: "pending" as const } : {}),
    };
  }
  // History may hold SCRUM-24 search traces and/or agent [{ name, ok }] entries.
  const tools = [
    ...toolUses(item.tool_trace),
    ...agentToolUses(item.tool_trace as unknown[]),
  ];
  return {
    id: `message-${item.id}`, serverId: item.id, role: "assistant",
    text: item.status === "INSUFFICIENT_CONTEXT" ? NO_CONTEXT_TEXT : item.content,
    // Prefer best-effort mapping so partial agent citations still render (SCRUM-23).
    citations: agentCitationViews(item.citations), tools,
  };
}

// Replace one message (a local "sending" bubble or a saved question) in place with
// saved messages, so a retried older question keeps its position in the thread.
export function replaceMessage(list: ChatMessage[], match: (message: ChatMessage) => boolean, saved: ConversationMessage[]) {
  const next = saved.map(toChatMessage);
  const savedIds = new Set(next.map((item) => item.id));
  const rest = list.filter((item) => !savedIds.has(item.id) || match(item));
  const index = rest.findIndex(match);
  return index === -1 ? [...rest, ...next] : [...rest.slice(0, index), ...next, ...rest.slice(index + 1)];
}
