"""A generator that returns fixed output without calling any API.

The default everywhere except a real run: free, instant, deterministic.
A failing test then means our code broke, not that a model wandered.
"""

from apps.notes.llm.base import (
    DEFAULT_NOTE_OPTIONS,
    validate_course_notes,
    validate_study_guide,
)

# How many points and concepts per section each detail level produces, so a
# change of detail level is visible in the output.
FAKE_ITEMS_PER_DETAIL = {"brief": 1, "standard": 2, "detailed": 4}


def _fake_point(number, words, note_format):
    if note_format == "paragraphs":
        return (
            f"Fake paragraph {number} from {words} words. It connects one idea to the next. "
            "It closes with what to remember."
        )
    return f"Fake point {number} from {words} words."


def _fake_concepts(count):
    terms = ["Fake term", *(f"Fake term {n}" for n in range(2, count + 1))]
    return [{"term": term, "explanation": "Fake explanation."} for term in terms]


class FakeStudyGuideLLM:
    """Every option changes the output in a way a test can see:
    type → which sections exist, detail → how many items, format → item style."""

    name = "fake"

    def generate_notes(self, sources, options=DEFAULT_NOTE_OPTIONS):
        count = FAKE_ITEMS_PER_DETAIL[options.detail_level]
        fmt = options.format

        if options.note_type == "summary":
            words = sum(len(text.split()) for _, text in sources)
            sections = [
                {
                    "heading": "Main themes",
                    "key_concepts": [],
                    "points": [_fake_point(n, words, fmt) for n in range(1, count + 1)],
                }
            ]
        elif options.note_type == "key_concepts":
            sections = [
                {"heading": title, "key_concepts": _fake_concepts(count + 1), "points": []}
                for title, _ in sources
            ]
        else:
            sections = [
                {
                    "heading": title,
                    "key_concepts": _fake_concepts(count),
                    "points": [_fake_point(n, len(text.split()), fmt) for n in range(1, count + 1)],
                }
                for title, text in sources
            ]

        return validate_course_notes(
            {
                "overview": (
                    f"Fake {options.note_type} overview of {len(sources)} materials "
                    f"({options.detail_level}, {fmt})."
                ),
                "sections": sections,
            },
            options,
        )

    def generate(self, text):
        return validate_study_guide(
            {
                "key_concepts": ["Fake concept A", "Fake concept B"],
                "important_points": ["Fake point 1", "Fake point 2"],
                "summary": f"Fake summary of {len(text.split())} words of text.",
            }
        )