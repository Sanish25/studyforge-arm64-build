from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agent.pandu.tools.memory import (
    prior_turns_for_prompt,
    recall_history,
    remember_turn,
)
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

    def _answered_pair(self, question: str, answer: str):
        asked = remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="user",
            content=question,
        )
        remember_turn(
            user=self.owner,
            conversation_id=self.conversation.id,
            role="assistant",
            content=answer,
            reply_to=asked["id"],
        )

    def test_prior_turns_for_prompt_skips_pending_failed_and_keeps_order(self):
        from django.utils import timezone

        self._answered_pair(
            "What is paging?",
            "Paging maps virtual to physical addresses.",
        )
        # PENDING / FAILED (even with text) must not enter the follow-up prompt.
        ConversationMessage.objects.create(
            conversation=self.conversation,
            role="user",
            status="PENDING",
            content="Still answering this?",
            attempted_at=timezone.now(),
        )
        ConversationMessage.objects.create(
            conversation=self.conversation,
            role="user",
            status="FAILED",
            content="This ask failed.",
            attempted_at=timezone.now(),
        )

        turns = prior_turns_for_prompt(self.conversation, limit=10)
        self.assertEqual(
            [row["content"] for row in turns],
            ["What is paging?", "Paging maps virtual to physical addresses."],
        )
        self.assertEqual([row["role"] for row in turns], ["user", "assistant"])

    def test_prior_turns_for_prompt_caps_newest_answered_pairs(self):
        for index in range(4):
            self._answered_pair(f"Q{index}", f"A{index}")
        # limit=2 → one newest completed pair (user + assistant).
        turns = prior_turns_for_prompt(self.conversation, limit=2)
        self.assertEqual([row["content"] for row in turns], ["Q3", "A3"])

    def test_prior_turns_default_window_is_eight(self):
        from apps.agent.pandu.tools.memory import AUTO_HISTORY_LIMIT

        self.assertEqual(AUTO_HISTORY_LIMIT, 8)
        for index in range(6):
            self._answered_pair(f"Q{index}", f"A{index}")
        turns = prior_turns_for_prompt(self.conversation)
        # 6 pairs = 12 messages; window keeps the newest 8 (4 pairs).
        self.assertEqual(len(turns), 8)
        self.assertEqual(
            [row["content"] for row in turns],
            ["Q2", "A2", "Q3", "A3", "Q4", "A4", "Q5", "A5"],
        )