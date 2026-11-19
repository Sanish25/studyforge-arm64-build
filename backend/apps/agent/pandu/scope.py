"""Hybrid scope gate: tiny fixed layer, then Gemini classify (architecture §4.1).

Three labels:
  IN_SCOPE     — may enter the tool loop
  OUT_OF_SCOPE — abstain (no tools)
  UNCLEAR      — clarify (ask a follow-up)

Fixed layer handles obvious cases without an LLM call. Everything else goes to
Gemini structured JSON, with one repair retry on bad shape.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from apps.agent.pandu.prompts import SCOPE_CLASSIFIER_PROMPT

ScopeLabel = Literal["IN_SCOPE", "OUT_OF_SCOPE", "UNCLEAR"]
ScopeSource = Literal["fixed", "gemini", "repair_failed"]

SCOPE_LABELS = frozenset({"IN_SCOPE", "OUT_OF_SCOPE", "UNCLEAR"})

SCOPE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["label", "needs_documents", "reason"],
    "properties": {
        "label": {"type": "string", "enum": sorted(SCOPE_LABELS)},
        "needs_documents": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "additionalProperties": False,
}

# Exact / near-exact allows only — keep this list tiny (architecture: ≤2–3).
_FIXED_ALLOWS: tuple[tuple[re.Pattern[str], bool, str], ...] = (
    (
        re.compile(r"\A(?:please\s+)?list\s+my\s+tasks\.?\Z", re.IGNORECASE),
        False,
        "Fixed allow: list tasks",
    ),
    (
        re.compile(r"\A(?:please\s+)?list\s+my\s+materials\.?\Z", re.IGNORECASE),
        False,
        "Fixed allow: list materials",
    ),
)

# Optional hard blocks — only clear, team-agreed patterns (not a topic encyclopedia).
_HARD_BLOCKS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
)

SCOPE_REPAIR_PROMPT = """
Your previous scope classification was invalid.
Return ONLY JSON with keys:
  label (IN_SCOPE | OUT_OF_SCOPE | UNCLEAR),
  needs_documents (boolean),
  reason (short string).
No other keys. No markdown.
""".strip()


class ScopeClassifierError(Exception):
    """Provider failure or unusable scope classifier output."""


class InvalidScopeOutput(ScopeClassifierError):
    """Malformed scope JSON from the classifier."""


@dataclass(frozen=True)
class ScopeDecision:
    label: ScopeLabel
    needs_documents: bool
    reason: str
    source: ScopeSource


ClassifyFn = Callable[[str, dict[str, Any]], dict[str, Any]]

# Cap titles sent to the classifier — hints only, not full-course RAG.
_MAX_READY_MATERIALS_FOR_SCOPE = 50


def _normalize_message(message: str) -> str:
    return " ".join(message.split()).strip()


def enrich_scope_context(user, context: dict[str, Any]) -> dict[str, Any]:
    """Add course_name and READY material titles for the Gemini classifier.

    Titles are classification hints only. Grounded answers still require the
    student to select document_ids (enforced in the loop).
    """
    enriched = dict(context)
    course_id = enriched.get("course_id")
    if course_id is None:
        return enriched

    from apps.documents.models import Document
    from apps.identity.ownership import owned_course

    course = owned_course(user, course_id)
    if course is None:
        return enriched

    if not enriched.get("course_name"):
        enriched["course_name"] = course.name

    if "ready_materials" not in enriched:
        rows = (
            Document.objects.filter(
                course=course,
                owner=user,
                status=Document.Status.READY,
                conversation__isnull=True,
            )
            .order_by("id")
            .values_list("id", "title")[:_MAX_READY_MATERIALS_FOR_SCOPE]
        )
        enriched["ready_materials"] = [
            {"id": document_id, "title": title} for document_id, title in rows
        ]
    return enriched


def _scope_classify_payload(message: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": message,
        "course_id": context.get("course_id"),
        "course_name": context.get("course_name"),
        "conversation_id": context.get("conversation_id"),
        "document_ids": context.get("document_ids") or [],
        "ready_materials": context.get("ready_materials") or [],
    }


def _parse_scope_payload(payload: Any) -> ScopeDecision:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, RecursionError) as exc:
            raise InvalidScopeOutput("Scope reply is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise InvalidScopeOutput("Scope reply must be a JSON object.")
    if set(payload) != {"label", "needs_documents", "reason"}:
        raise InvalidScopeOutput("Scope reply has invalid fields.")
    label = payload.get("label")
    needs_documents = payload.get("needs_documents")
    reason = payload.get("reason")
    if label not in SCOPE_LABELS:
        raise InvalidScopeOutput("Scope label is invalid.")
    if not isinstance(needs_documents, bool):
        raise InvalidScopeOutput("needs_documents must be a boolean.")
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidScopeOutput("reason must be a nonempty string.")
    return ScopeDecision(
        label=label,  # type: ignore[arg-type]
        needs_documents=needs_documents,
        reason=reason.strip(),
        source="gemini",
    )


def fixed_scope(message: str) -> ScopeDecision | None:
    """Deterministic gate. Returns a decision or None to fall through to Gemini."""
    normalized = _normalize_message(message)
    if not normalized:
        return ScopeDecision(
            label="UNCLEAR",
            needs_documents=False,
            reason="Empty message",
            source="fixed",
        )

    for pattern in _HARD_BLOCKS:
        if pattern.search(normalized):
            return ScopeDecision(
                label="OUT_OF_SCOPE",
                needs_documents=False,
                reason="Hard safety block",
                source="fixed",
            )

    for pattern, needs_documents, reason in _FIXED_ALLOWS:
        if pattern.fullmatch(normalized):
            return ScopeDecision(
                label="IN_SCOPE",
                needs_documents=needs_documents,
                reason=reason,
                source="fixed",
            )

    return None


class FakeScopeClassifier:
    """Offline default: unclear so the loop clarifies rather than inventing tools."""

    name = "fake"

    def classify(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        del message, context
        return {
            "label": "UNCLEAR",
            "needs_documents": False,
            "reason": "Fake scope classifier; configure PANDU_SCOPE_BACKEND=gemini for live classify.",
        }


class GeminiScopeClassifier:
    def __init__(self, client=None):
        from apps.gemini import GeminiJSONClient

        self._gemini = GeminiJSONClient(
            "PANDU_SCOPE_MODEL",
            ScopeClassifierError,
            InvalidScopeOutput,
            client=client,
        )
        self.name = self._gemini.name

    def classify(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        user_payload = json.dumps(_scope_classify_payload(message, context))
        messages = [
            {"role": "system", "content": SCOPE_CLASSIFIER_PROMPT},
            {"role": "user", "content": user_payload},
        ]
        raw = self._gemini.complete(
            messages, schema=SCOPE_JSON_SCHEMA, max_output_tokens=256
        )
        return json.loads(raw)


def get_scope_classifier(client=None):
    backend = os.environ.get("PANDU_SCOPE_BACKEND", "fake").strip().lower()
    if backend == "fake":
        return FakeScopeClassifier()
    if backend == "gemini":
        return GeminiScopeClassifier(client=client)
    raise ScopeClassifierError("PANDU_SCOPE_BACKEND must be fake or gemini.")


class _FnClassifier:
    """Adapter so tests can inject a plain ``classify(message, context)`` function."""

    def __init__(self, fn: ClassifyFn):
        self._fn = fn

    def classify(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._fn(message, context)


def _resolve_classifier(classifier):
    if classifier is None:
        return get_scope_classifier()
    if hasattr(classifier, "classify") and callable(classifier.classify):
        return classifier
    if callable(classifier):
        return _FnClassifier(classifier)
    raise ScopeClassifierError("Scope classifier must provide classify().")


def _classify_with_repair(
    message: str,
    context: dict[str, Any],
    classifier,
) -> ScopeDecision:
    """One classify attempt, then one repair; then safe UNCLEAR."""
    try:
        return _parse_scope_payload(classifier.classify(message, context))
    except (ScopeClassifierError, TypeError, ValueError):
        pass

    try:
        if isinstance(classifier, GeminiScopeClassifier):
            user_payload = json.dumps({"message": message})
            messages = [
                {"role": "system", "content": SCOPE_CLASSIFIER_PROMPT},
                {"role": "user", "content": user_payload},
                {"role": "assistant", "content": "{}"},
                {"role": "system", "content": SCOPE_REPAIR_PROMPT},
            ]
            raw = classifier._gemini.complete(
                messages, schema=SCOPE_JSON_SCHEMA, max_output_tokens=256
            )
            return _parse_scope_payload(raw)
        return _parse_scope_payload(classifier.classify(message, context))
    except (ScopeClassifierError, TypeError, ValueError):
        return ScopeDecision(
            label="UNCLEAR",
            needs_documents=False,
            reason="Scope classification failed; ask the student to clarify.",
            source="repair_failed",
        )


def check_scope(
    *,
    user,
    message: str,
    context: dict[str, Any] | None = None,
    classifier=None,
) -> ScopeDecision:
    """Hybrid scope: fixed layer first, then Gemini (or injected) classifier.

    ``user`` is required so callers always pass the JWT principal; ownership
    401/404 stay at the HTTP layer before this runs.
    """
    if user is None:
        raise ScopeClassifierError("Authenticated user is required for scope checks.")

    context = enrich_scope_context(user, context or {})
    fixed = fixed_scope(message if isinstance(message, str) else "")
    if fixed is not None:
        return fixed

    active = _resolve_classifier(classifier)
    return _classify_with_repair(_normalize_message(message), context, active)
