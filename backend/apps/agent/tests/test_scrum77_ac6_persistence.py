"""SCRUM-77 AC6: tests cover saving, loading, continuing, deleting, and ownership.

Agent-path persistence (POST /agent/pandu/) plus conversation history/delete APIs.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.conversations.models import Conversation, ConversationMessage
from apps.courses.models import Course

AGENT_URL = "/api/v1/agent/pandu/"


def _envelope(**overrides):
    body = {
        "type": "message",
        "status": "ok",
        "text": "Paging maps virtual addresses to frames.",
        "citations": [
            {
                "chunk_id": 1,
                "document_id": 9,
                "page_number": 2,
                "excerpt": "Paging uses page tables.",
            }
        ],
        "tool_trace": [{"name": "ask_course_question", "ok": True}],
    }
    body.update(overrides)
    return body


class Scrum77Ac6PersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="scrum77-owner@example.test")
        cls.other = user_model.objects.create_user(email="scrum77-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="SCRUM-77 course")
        cls.other_course = Course.objects.create(owner=cls.other, name="Foreign")
        cls.conversation = Conversation.objects.create(
            owner=cls.owner, course=cls.course, title=""
        )
        cls.other_conversation = Conversation.objects.create(
            owner=cls.other, course=cls.other_course, title="Secret"
        )

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}"
        )
        self.foreign = APIClient()
        self.foreign.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.other)}"
        )

    def _ask(self, message: str, *, conversation=None, course=None, client=None):
        conversation = conversation or self.conversation
        course = course or self.course
        http = client or self.client
        return http.post(
            AGENT_URL,
            {
                "message": message,
                "course_id": course.id,
                "conversation_id": conversation.id,
            },
            format="json",
        )

    def _history(self, conversation=None, *, client=None):
        conversation = conversation or self.conversation
        http = client or self.client
        return http.get(f"/api/v1/conversations/{conversation.id}/messages/")

    # --- saving --------------------------------------------------------------

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_saving_persists_question_reply_citations_and_tools(self, _mocked):
        response = self._ask("What is paging?")
        self.assertEqual(response.status_code, 200)

        rows = list(
            ConversationMessage.objects.filter(conversation=self.conversation).order_by(
                "created_at", "id"
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].role, "user")
        self.assertEqual(rows[0].status, ConversationMessage.Status.ANSWERED)
        self.assertEqual(rows[0].content, "What is paging?")
        self.assertEqual(rows[1].role, "assistant")
        self.assertEqual(rows[1].content, "Paging maps virtual addresses to frames.")
        self.assertEqual(rows[1].reply_to_id, rows[0].id)
        self.assertEqual(rows[1].citations[0]["excerpt"], "Paging uses page tables.")
        self.assertEqual(rows[1].tool_trace[0]["name"], "ask_course_question")

    # --- loading -------------------------------------------------------------

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_loading_returns_messages_in_chronological_order(self, _mocked):
        self._ask("What is paging?")
        history = self._history()
        self.assertEqual(history.status_code, 200)
        body = history.json()
        self.assertEqual([row["role"] for row in body], ["user", "assistant"])
        self.assertEqual(body[0]["content"], "What is paging?")
        self.assertEqual(
            body[1]["content"], "Paging maps virtual addresses to frames."
        )
        self.assertEqual(body[1]["tool_trace"][0]["name"], "ask_course_question")
        # Citations stay on the saved reply after reload.
        self.assertTrue(isinstance(body[1]["citations"], list))
        self.assertGreaterEqual(len(body[1]["citations"]), 1)

    # --- continuing ----------------------------------------------------------

    def test_continuing_injects_completed_pairs_as_prior_messages(self):
        with patch(
            "apps.agent.views.run_pandu_turn",
            return_value=_envelope(text="Paging maps virtual addresses to frames."),
        ):
            self.assertEqual(self._ask("What is paging?").status_code, 200)

        with patch(
            "apps.agent.views.run_pandu_turn",
            return_value=_envelope(text="Think of a library card catalog."),
        ) as mocked:
            response = self._ask("Give me an analogy for that")
        self.assertEqual(response.status_code, 200)

        prior = mocked.call_args.kwargs["context"]["prior_messages"]
        self.assertEqual(
            [row["content"] for row in prior],
            [
                "What is paging?",
                "Paging maps virtual addresses to frames.",
            ],
        )
        self.assertNotIn(
            "Give me an analogy for that",
            [row["content"] for row in prior],
        )

        history = self._history().json()
        self.assertEqual(len(history), 4)
        self.assertEqual(history[2]["content"], "Give me an analogy for that")
        self.assertEqual(history[3]["content"], "Think of a library card catalog.")

    # --- deleting ------------------------------------------------------------

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_deleting_conversation_removes_its_messages(self, _mocked):
        self._ask("What is paging?")
        self.assertTrue(ConversationMessage.objects.filter(conversation=self.conversation).exists())

        deleted = self.client.delete(f"/api/v1/conversations/{self.conversation.id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.id).exists())
        self.assertFalse(ConversationMessage.objects.filter(conversation_id=self.conversation.id).exists())

        missing = self._history()
        self.assertEqual(missing.status_code, 404)

    # --- ownership -----------------------------------------------------------

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_ownership_hides_foreign_list_read_delete_and_ask(self, mocked):
        self._ask("What is paging?")

        # Foreign student cannot read, delete, or ask into the owner's chat.
        self.assertEqual(self._history(client=self.foreign).status_code, 404)
        self.assertEqual(
            self.foreign.delete(f"/api/v1/conversations/{self.conversation.id}/").status_code,
            404,
        )
        self.assertEqual(
            self._ask("leak?", client=self.foreign).status_code,
            404,
        )
        # Owner history still intact; foreign ask did not create rows on this chat.
        self.assertEqual(self._history().status_code, 200)
        self.assertEqual(
            ConversationMessage.objects.filter(conversation=self.conversation).count(),
            2,
        )
        # Foreign conversation stays unreachable to the owner as well.
        self.assertEqual(self._history(self.other_conversation).status_code, 404)
        mocked.assert_called_once()  # only the owner's successful ask
