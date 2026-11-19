import json

from django.test import SimpleTestCase

from apps.agent.pandu.schema import (
    DEFAULT_ERROR_TEXT,
    InvalidReply,
    enforce_reply,
    error_reply,
    parse_reply,
    validate_reply,
)


def _valid(**overrides):
    payload = {
        "type": "message",
        "status": "ok",
        "text": "You have two open tasks.",
        "citations": [],
        "tool_trace": [{"name": "list_tasks", "ok": True}],
    }
    payload.update(overrides)
    return payload


class ParseReplyTests(SimpleTestCase):
    def test_accepts_valid_envelope(self):
        result = parse_reply(_valid())
        self.assertEqual(result["type"], "message")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tool_trace"][0]["name"], "list_tasks")

    def test_parses_json_string(self):
        result = parse_reply(json.dumps(_valid(status="clarify", text="Pick a PDF.")))
        self.assertEqual(result["status"], "clarify")

    def test_defaults_omitted_tool_trace(self):
        payload = _valid()
        del payload["tool_trace"]
        result = parse_reply(payload)
        self.assertEqual(result["tool_trace"], [])

    def test_rejects_unknown_fields(self):
        with self.assertRaises(InvalidReply) as ctx:
            parse_reply(_valid(extra="nope"))
        self.assertIn("Unknown reply fields", ctx.exception.reason)

    def test_rejects_empty_text(self):
        with self.assertRaises(InvalidReply):
            parse_reply(_valid(text="  "))

    def test_rejects_bad_status(self):
        with self.assertRaises(InvalidReply):
            parse_reply(_valid(status="maybe"))

    def test_rejects_non_object_citations(self):
        with self.assertRaises(InvalidReply):
            parse_reply(_valid(citations=["not-an-object"]))


class EnforceReplyTests(SimpleTestCase):
    def test_valid_payload_skips_repair(self):
        calls = []

        def repair(payload, reason):
            calls.append((payload, reason))
            return payload

        result = enforce_reply(_valid(), repair=repair)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(calls, [])

    def test_one_successful_repair(self):
        calls = []

        def repair(payload, reason):
            calls.append(reason)
            return _valid(text="Repaired answer.")

        result = enforce_reply({"type": "message", "status": "ok"}, repair=repair)
        self.assertEqual(result["text"], "Repaired answer.")
        self.assertEqual(len(calls), 1)

    def test_failed_repair_returns_error_envelope(self):
        def repair(payload, reason):
            return {"type": "message", "status": "ok", "text": ""}

        result = enforce_reply("not-json", repair=repair)
        self.assertEqual(result, error_reply())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["text"], DEFAULT_ERROR_TEXT)
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["tool_trace"], [])

    def test_repair_exception_returns_error_envelope(self):
        def repair(payload, reason):
            raise RuntimeError("provider down")

        result = enforce_reply(_valid(status="nope"), repair=repair)
        self.assertEqual(result["status"], "error")

    def test_without_repair_returns_error_envelope(self):
        result = enforce_reply({"status": "ok"})
        self.assertEqual(result["status"], "error")

    def test_validate_reply_does_not_repair(self):
        result = validate_reply(_valid(type="chat"))
        self.assertEqual(result["status"], "error")
