"""Agent HTTP routes under /api/v1/."""

from django.db import transaction
from django.urls import path

from apps.agent.views import PanduAgentView

urlpatterns = [
    # Non-atomic: Gemini/tool work must not run inside a request-wide transaction.
    path(
        "agent/pandu/",
        transaction.non_atomic_requests(PanduAgentView.as_view()),
        name="agent-pandu",
    ),
]
