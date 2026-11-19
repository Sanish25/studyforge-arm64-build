"""Pandu tool handlers. Domain logic stays in conversations/knowledge/notes/quizzes/courses."""

# Import tool modules for side-effect registration with the registry.
from apps.agent.pandu.tools import courses as courses  # noqa: F401
from apps.agent.pandu.tools import materials as materials  # noqa: F401
from apps.agent.pandu.tools import memory as memory  # noqa: F401
from apps.agent.pandu.tools import notes as notes  # noqa: F401
from apps.agent.pandu.tools import quizzes as quizzes  # noqa: F401
from apps.agent.pandu.tools import rag as rag  # noqa: F401
from apps.agent.pandu.tools import tasks as tasks  # noqa: F401


