from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.conversations.models import Conversation, ConversationMessage
from apps.courses.models import Course


URL = "/api/v1/agent/pandu/"


def _envelope(**overrides):
    body = {
        "type": "message",
        "status": "ok",
        "text": "You have 1 open task.",
        "citations": [],
        "tool_trace": [{"name": "list_tasks", "ok": True}],
    }
    body.update(overrides)
    return body


class PanduEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="pandu-owner@example.test")
        cls.other = user_model.objects.create_user(email="pandu-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Agent course")
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

    def test_unauthenticated_is_401(self):
        self.client.credentials()
        response = self.client.post(URL, {"message": "list my tasks"}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "AUTHENTICATION_REQUIRED")

    def test_foreign_conversation_is_404(self):
        response = self.client.post(
            URL,
            {
                "message": "list my tasks",
                "conversation_id": self.other_conversation.id,
                "course_id": self.course.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ConversationMessage.objects.exists())

    def test_invalid_body_is_400(self):
        response = self.client.post(
            URL, {"document_ids": [1, 1], "message": "hi"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_REQUEST")

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_turn_returns_envelope_and_persists(self, mocked_turn):
        response = self.client.post(
            URL,
            {
                "message": "list my tasks",
                "course_id": self.course.id,
                "conversation_id": self.conversation.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["type"], "message")
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["text"], "You have 1 open task.")
        self.assertEqual(body["tool_trace"][0]["name"], "list_tasks")

        mocked_turn.assert_called_once()
        kwargs = mocked_turn.call_args.kwargs
        self.assertEqual(kwargs["user"], self.owner)
        self.assertEqual(kwargs["message"], "list my tasks")
        self.assertEqual(kwargs["context"]["course_id"], self.course.id)
        self.assertEqual(kwargs["context"]["course_name"], self.course.name)
        self.assertEqual(kwargs["context"]["conversation_id"], self.conversation.id)
        self.assertEqual(kwargs["context"]["prior_messages"], [])

        messages = list(
            ConversationMessage.objects.filter(conversation=self.conversation).order_by(
                "created_at", "id"
            )
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "list my tasks")
        self.assertEqual(messages[0].status, ConversationMessage.Status.ANSWERED)
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, "You have 1 open task.")
        self.assertEqual(messages[1].reply_to_id, messages[0].id)

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "list my tasks")

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope(
        text="A library card is like a page table entry.",
    ))
    def test_follow_up_passes_prior_messages_without_duplicating_ask(self, mocked_turn):
        """SCRUM-77: earlier turns are loaded before saving the new question."""
        from apps.agent.pandu.tools.memory import remember_turn

        asked = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="user",
            content="What is virtual memory?",
        )
        remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="assistant",
            content="Virtual memory maps addresses to frames.",
            reply_to=asked["id"],
        )

        response = self.client.post(
            URL,
            {
                "message": "Give me an analogy for that",
                "course_id": self.course.id,
                "conversation_id": self.conversation.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        prior = mocked_turn.call_args.kwargs["context"]["prior_messages"]
        self.assertEqual(
            [row["content"] for row in prior],
            [
                "What is virtual memory?",
                "Virtual memory maps addresses to frames.",
            ],
        )
        # Current ask is saved after the load, so it must not be in prior_messages.
        self.assertNotIn(
            "Give me an analogy for that",
            [row["content"] for row in prior],
        )

        saved = list(
            ConversationMessage.objects.filter(conversation=self.conversation).order_by(
                "created_at", "id"
            )
        )
        self.assertEqual(saved[-2].content, "Give me an analogy for that")
        self.assertEqual(
            saved[-1].content,
            "A library card is like a page table entry.",
        )

    @patch("apps.agent.views.run_pandu_turn", return_value=_envelope())
    def test_without_conversation_does_not_persist(self, mocked_turn):
        response = self.client.post(
            URL,
            {"message": "list my tasks", "course_id": self.course.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        mocked_turn.assert_called_once()
        self.assertFalse(ConversationMessage.objects.exists())

    @patch("apps.agent.views.run_pandu_turn", side_effect=RuntimeError("boom"))
    def test_loop_crash_marks_question_failed(self, _mocked_turn):
        response = self.client.post(
            URL,
            {
                "message": "list my tasks",
                "conversation_id": self.conversation.id,
                "course_id": self.course.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        question = ConversationMessage.objects.get(role="user")
        self.assertEqual(question.status, ConversationMessage.Status.FAILED)
        self.assertFalse(
            ConversationMessage.objects.filter(role="assistant").exists()
        )
