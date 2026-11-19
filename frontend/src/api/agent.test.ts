import { afterEach, expect, it, vi } from "vitest";
import { askPanduAgent } from "./agent";
import { DocumentRequestError } from "./documents";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("posts the agent payload and returns the JSON envelope", async () => {
  const fetch = vi.fn().mockResolvedValue(
    Response.json({
      type: "message",
      status: "ok",
      text: "You have 1 open task.",
      citations: [],
      tool_trace: [{ name: "list_tasks", ok: true }],
    }),
  );
  vi.stubGlobal("fetch", fetch);

  const result = await askPanduAgent(
    {
      message: "list my tasks",
      course_id: 42,
      conversation_id: 9,
      document_ids: [1],
    },
    "token",
    new AbortController().signal,
  );

  expect(fetch.mock.calls[0][0]).toBe("http://api.test/api/v1/agent/pandu/");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    message: "list my tasks",
    course_id: 42,
    conversation_id: 9,
    document_ids: [1],
  });
  expect(result.status).toBe("ok");
  expect(result.text).toBe("You have 1 open task.");
});

it("maps non-OK HTTP responses to DocumentRequestError", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json({ code: "RESOURCE_NOT_FOUND", message: "Resource not found." }, { status: 404 }),
    ),
  );
  await expect(
    askPanduAgent({ message: "hi", conversation_id: 9 }, "token", new AbortController().signal),
  ).rejects.toBeInstanceOf(DocumentRequestError);
});
