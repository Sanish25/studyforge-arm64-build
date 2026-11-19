from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agent.pandu.tools.memory import recall_history, remember_turn
from apps.agent.pandu.tools.registry import get_tool
from apps.conversations.models import Conversation, ConversationMessage
from apps.courses.models import Course


class MemoryToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="memory-owner@example.test")
        cls.other = user_model.objects.create_user(email="memory-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Memory course")
        cls.other_course = Course.objects.create(owner=cls.other, name="Foreign course")
        cls.conversation = Conversation.objects.create(
            owner=cls.owner, course=cls.course, title=""
        )
        cls.other_conversation = Conversation.objects.create(
            owner=cls.other, course=cls.other_course, title="Secret"
        )

    def test_tools_registered(self):
        self.assertFalse(get_tool("recall_history").mutates)
        self.assertTrue(get_tool("remember_turn").mutates)

    def test_remember_and_recall_round_trip(self):
        asked = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="user",
            content="What is paging?",
        )
        self.assertTrue(asked["ok"])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, "What is paging?")

        answered = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="assistant",
            content="Paging maps virtual addresses to physical frames.",
            reply_to=asked["id"],
        )
        self.assertTrue(answered["ok"])

        history = recall_history(
            user=self.owner, conversation_id=self.conversation.id
        )
        self.assertTrue(history["ok"])
        self.assertEqual(
            [row["role"] for row in history["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(history["messages"][0]["content"], "What is paging?")
        self.assertEqual(
            history["messages"][1]["content"],
            "Paging maps virtual addresses to physical frames.",
        )

    def test_recall_foreign_conversation(self):
        result = recall_history(
            user=self.owner, conversation_id=self.other_conversation.id
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_remember_foreign_conversation(self):
        result = remember_turn(
            user=self.owner,
            conversation_id=self.other_conversation.id,
            role="user",
            content="leak?",
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
        self.assertFalse(
            ConversationMessage.objects.filter(
                conversation=self.other_conversation
            ).exists()
        )

    def test_remember_rejects_tool_role(self):
        result = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="tool",
            content={"ok": True},
        )
        self.assertEqual(result["code"], "INVALID_REQUEST")

    def test_assistant_without_open_question(self):
        result = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="assistant",
            content="orphan reply",
        )
        self.assertEqual(result["code"], "INVALID_REQUEST")

    def test_recall_limit_window_oldest_to_newest(self):
        for index in range(5):
            remember_turn(
                user=self.owner,
                conversation_id=self.conversation.id,
                role="user",
                content=f"Q{index}",
            )
        history = recall_history(
            user=self.owner, conversation_id=self.conversation.id, limit=2
        )
        self.assertTrue(history["ok"])
        self.assertEqual(len(history["messages"]), 2)
        self.assertEqual(
            [row["content"] for row in history["messages"]],
            ["Q3", "Q4"],
        )
