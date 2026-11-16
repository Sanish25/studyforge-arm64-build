import { afterEach, expect, it, vi } from "vitest";
import { generateNotes, getNotes, NotesRequestError } from "./notes";

const notes = { id: 5, title: "Notes: Cells", course: 42, overview: "x", sections: [], source_documents: [], created_at: "2026-10-01" };
afterEach(() => vi.unstubAllGlobals());

const choices = { note_type: "key_concepts", detail_level: "detailed", format: "paragraphs" } as const;

it("posts the selected ids and options to the course notes endpoint", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(notes, { status: 201 }));
  vi.stubGlobal("fetch", fetch);
  expect(await generateNotes(42, [1, 2], choices, "token")).toEqual(notes);
  const [url, options] = fetch.mock.calls[0];
  expect(url).toMatch(/\/courses\/42\/notes\/$/);
  expect(options.method).toBe("POST");
  expect(JSON.parse(options.body)).toEqual({ document_ids: [1, 2], ...choices });
  expect(options.headers.get("Authorization")).toBe("Bearer token");
});

it("reads saved notes without using the browser cache", async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(notes));
  vi.stubGlobal("fetch", fetch);
  expect(await getNotes(5, "token")).toEqual(notes);
  expect(fetch.mock.calls[0][0]).toMatch(/\/notes\/5\/$/);
  expect(fetch.mock.calls[0][1].cache).toBe("no-store");
});

it("carries the backend's code on a failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ code: "NOTES_INPUT_TOO_LARGE" }, { status: 422 })));
  await expect(generateNotes(42, [1], choices, "token")).rejects.toMatchObject({ status: 422, code: "NOTES_INPUT_TOO_LARGE" });
});

it("falls back to an empty code when the failure is not JSON", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })));
  const failure = await getNotes(5, "token").catch((cause: unknown) => cause);
  expect(failure).toBeInstanceOf(NotesRequestError);
  expect(failure).toMatchObject({ status: 502, code: "" });
});
