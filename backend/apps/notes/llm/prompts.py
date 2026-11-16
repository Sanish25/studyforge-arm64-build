"""The notes system prompt, assembled from fixed fragments per option.

Only NoteOptions values (fixed lists, checked on construction) pick the text
below. Nothing a student types is ever placed in these instructions.
"""

from apps.notes.llm.base import DETAIL_LEVELS, NOTE_FORMATS, NOTE_TYPES

NOTES_BASE_PROMPT = """You write organized study notes from a student's own course
materials. Each material appears under a "## " heading carrying its title. The
materials may come from any subject and any format.

Grounding rules:
- Use ONLY the material text provided. Never add outside knowledge, even where
  it is incomplete, or where you know more about the topic than it does.
- Every item must be traceable to something the materials actually state.
- If the materials are too thin to support many items, return fewer rather than
  padding with generic knowledge about the topic.

Organizing rules:
- Group by topic. Where several materials cover the same topic, consolidate them
  into one section instead of repeating it per material.
- Keep distinct topics in the order the materials present them.

Writing rules:
- Write for a student revising this material for an exam.
- Preserve the materials' own terminology, notation and symbols.
- Reproduce formulas, dates, names, figures and citations exactly as written.
- No meta-commentary. Never write "the document", "this lecture", "the material",
  "the materials", "these notes", "the text", "the author", "covers", "focuses",
  or "discusses"."""

NOTE_TYPE_RULES = {
    "summary": """Note type: SUMMARY.
- The overview carries most of the content: state the main ideas and how they
  connect.
- Use a few sections, one per major theme, not one per minor topic.
- Each section's points are the takeaways a student must remember.
- Include key concepts only for terms essential to understanding; a section may
  have none.""",
    "outline": """Note type: OUTLINE.
- Mirror the structure of the materials: one section per topic, in the order the
  materials present them.
- Points follow the order of the material within each topic. Every section has
  points.
- Add key concepts for the terms each topic defines.""",
    "key_concepts": """Note type: KEY CONCEPTS.
- The notes are a study glossary. Every section has key concepts, and they are
  the main content.
- Group related terms under a shared topic heading.
- Use points only for relationships, contrasts or conditions that link the
  concepts in that section; a section may have no points.""",
}

DETAIL_LEVEL_RULES = {
    "brief": """Detail level: BRIEF.
- Keep only the main ideas. Leave out examples, side notes and minor details.
- Use 2 to 4 sections, with at most 3 key concepts and at most 3 points each.
- Each explanation is one short sentence. The overview is 1 to 2 sentences.""",
    "standard": """Detail level: STANDARD.
- Cover every topic the materials explain, including those near the end. Longer
  input needs more sections and items, never a shorter summary.
- Keep every distinct definition, rule, value, date and name.
- Each explanation is one or two sentences. The overview is a short paragraph.""",
    "detailed": """Detail level: DETAILED.
- Cover every topic the materials explain, including those near the end. Longer
  input needs more sections and items, never a shorter summary.
- Keep every distinct definition, rule, value, date and name, and also the
  examples, worked results, conditions and exceptions the materials give.
- Split large topics into separate sections for their subtopics.
- Each explanation is two or three sentences. The overview is a full paragraph.""",
}

NOTE_FORMAT_RULES = {
    "bullets": """Format: BULLET POINTS.
- Each item in "points" is one concise sentence or fragment that stands alone as
  a bullet. Never put several ideas in one point.""",
    "paragraphs": """Format: PARAGRAPHS.
- Each item in "points" is a paragraph of 3 to 5 connected sentences, written as
  prose that explains how the ideas relate. Never write a list inside a point.""",
}

NOTES_RESPONSE_SHAPE = """Respond with a JSON object in exactly this shape:

{
  "overview": "Prose stating the main ideas themselves, not what the materials
    are about.",
  "sections": [
    {
      "heading": "A short topic heading",
      "key_concepts": [
        {"term": "A term the materials explain",
         "explanation": "As the materials define it."}
      ],
      "points": ["A specific claim worth remembering that is not already a key
        concept: a rule, relationship, result, condition, exception, or date."]
    }
  ]
}

Every section has both "key_concepts" and "points". Use [] for a list a section
does not need; never leave a key out."""

# Every option value must have its fragment; tests check this too.
assert set(NOTE_TYPE_RULES) == set(NOTE_TYPES)
assert set(DETAIL_LEVEL_RULES) == set(DETAIL_LEVELS)
assert set(NOTE_FORMAT_RULES) == set(NOTE_FORMATS)


def build_notes_prompt(options):
    """The system prompt for one set of options."""
    return "\n\n".join(
        (
            NOTES_BASE_PROMPT,
            NOTE_TYPE_RULES[options.note_type],
            DETAIL_LEVEL_RULES[options.detail_level],
            NOTE_FORMAT_RULES[options.format],
            NOTES_RESPONSE_SHAPE,
        )
    )
