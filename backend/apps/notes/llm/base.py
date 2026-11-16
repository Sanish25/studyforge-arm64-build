"""What every study-guide generator must satisfy, and the validator
that stands between a model and our database."""

from dataclasses import dataclass

REQUIRED_KEYS = ("key_concepts", "important_points", "summary")

# The option values, mirrored from apps.notes.models so the llm package needs
# no Django models. A test keeps the two in step.
NOTE_TYPES = ("summary", "outline", "key_concepts")
DETAIL_LEVELS = ("brief", "standard", "detailed")
NOTE_FORMATS = ("bullets", "paragraphs")


@dataclass(frozen=True)
class NoteOptions:
    """How a set of notes is written. Values come only from the fixed lists."""

    note_type: str = "outline"
    detail_level: str = "standard"
    format: str = "bullets"

    def __post_init__(self):
        for value, allowed in (
            (self.note_type, NOTE_TYPES),
            (self.detail_level, DETAIL_LEVELS),
            (self.format, NOTE_FORMATS),
        ):
            if value not in allowed:
                raise ValueError(f"Unknown note option {value!r}")


DEFAULT_NOTE_OPTIONS = NoteOptions()


class LLMError(Exception):
    """The provider failed in a way we cannot recover from."""


class InvalidLLMOutput(LLMError):
    """The provider returned something that is not a valid study guide."""


class NotesMergeTooLargeError(LLMError):
    """Batch notes came back too large to merge in one call. A size problem the
    student can fix (fewer materials, lower detail), not a provider outage."""


def validate_study_guide(payload):
    """Reject anything that is not a well-formed study guide.

    Model output is untrusted input. It can be prose instead of JSON,
    truncated mid-object, or the right keys holding the wrong types.
    Nothing unvalidated reaches the database.
    """
    if not isinstance(payload, dict):
        raise InvalidLLMOutput(f"Expected an object, got {type(payload).__name__}")

    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise InvalidLLMOutput(f"Missing keys: {', '.join(missing)}")

    for key in ("key_concepts", "important_points"):
        value = payload[key]
        if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
            raise InvalidLLMOutput(f"{key} must be a list of strings")
        if not value:
            raise InvalidLLMOutput(f"{key} came back empty")

    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise InvalidLLMOutput("summary must be a non-empty string")

    # Return only our keys — a model that adds extras doesn't get to store them.
    return {key: payload[key] for key in REQUIRED_KEYS}


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InvalidLLMOutput(f"{label} must be a non-empty string")
    return value.strip()


def _validate_key_concept(concept):
    if not isinstance(concept, dict):
        raise InvalidLLMOutput("key_concepts must hold objects")
    return {
        "term": _required_text(concept.get("term"), "term"),
        "explanation": _required_text(concept.get("explanation"), "explanation"),
    }


def _validate_section(section):
    if not isinstance(section, dict):
        raise InvalidLLMOutput("sections must hold objects")

    # Summary sections may have no key concepts and key-concepts sections no
    # points; the model often omits such a list rather than sending [].
    key_concepts = section.get("key_concepts", [])
    points = section.get("points", [])
    if not isinstance(key_concepts, list) or not isinstance(points, list):
        raise InvalidLLMOutput("key_concepts and points must be lists")
    if not key_concepts and not points:
        raise InvalidLLMOutput("A section needs key concepts or points")

    return {
        "heading": _required_text(section.get("heading"), "heading"),
        "key_concepts": [_validate_key_concept(concept) for concept in key_concepts],
        "points": [_required_text(point, "point") for point in points],
    }


def _check_note_type(sections, note_type):
    """Structure each note type promises. Counts and lengths are prompt targets,
    not rules: rejecting a slightly long "brief" note would only cost a retry."""
    if note_type == "key_concepts":
        if not all(section["key_concepts"] for section in sections):
            raise InvalidLLMOutput("Every key-concepts section needs key concepts")
    elif note_type == "outline":
        if not all(section["points"] for section in sections):
            raise InvalidLLMOutput("Every outline section needs points")
        if not any(section["key_concepts"] for section in sections):
            raise InvalidLLMOutput("Notes need at least one key concept")
    # A summary may leave key concepts out entirely; _validate_section already
    # requires every section to say something.


def validate_course_notes(payload, options=DEFAULT_NOTE_OPTIONS):
    """The validate_study_guide contract, for headed multi-material notes."""
    if not isinstance(payload, dict):
        raise InvalidLLMOutput(f"Expected an object, got {type(payload).__name__}")

    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise InvalidLLMOutput("sections must be a non-empty list")

    validated = [_validate_section(section) for section in sections]
    _check_note_type(validated, options.note_type)

    return {
        "overview": _required_text(payload.get("overview"), "overview"),
        "sections": validated,
    }