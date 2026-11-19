from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from apps.agent.pandu.tools.rag import (
    answer_from_sources,
    ask_course_question,
    retrieve_chunks,
)
from apps.agent.pandu.tools.registry import get_tool
from apps.conversations.models import Conversation
from apps.courses.models import Course
from apps.knowledge.llm import InvalidCitation
from apps.knowledge.services import RAGServiceError


class RagToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="rag-owner@example.test")
        cls.other = user_model.objects.create_user(email="rag-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="RAG course")
        cls.conversation = Conversation.objects.create(
            owner=cls.owner, course=cls.course, title="Course chat"
        )
        cls.other_conversation = Conversation.objects.create(
            owner=cls.other, title="Foreign chat"
        )

    def test_tools_are_registered(self):
        for name in ("retrieve_chunks", "ask_course_question", "answer_from_sources"):
            self.assertIsNotNone(get_tool(name))
            self.assertFalse(get_tool(name).mutates)

    @patch("apps.agent.pandu.tools.rag.retrieve_chunks_for_documents")
    def test_retrieve_chunks_maps_passages(self, retrieve):
        retrieve.return_value = [
            {
                "chunk_id": 7,
                "document_id": 3,
                "page_number": 2,
                "content": "Paging moves frames.",
                "score": 0.91,
            }
        ]

        result = retrieve_chunks(
            user=self.owner,
            question="What is paging?",
            document_ids=[3],
            conversation_id=self.conversation.id,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["passages"],
            [
                {
                    "chunk_id": 7,
                    "document_id": 3,
                    "page": 2,
                    "text": "Paging moves frames.",
                    "score": 0.91,
                }
            ],
        )
        retrieve.assert_called_once()

    @patch("apps.agent.pandu.tools.rag.retrieve_chunks_for_documents")
    def test_retrieve_chunks_foreign_conversation(self, retrieve):
        result = retrieve_chunks(
            user=self.owner,
            question="What is paging?",
            document_ids=[3],
            conversation_id=self.other_conversation.id,
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
        retrieve.assert_not_called()

    @patch("apps.agent.pandu.tools.rag.retrieve_chunks_for_documents", side_effect=Http404)
    def test_retrieve_chunks_missing_documents(self, _retrieve):
        result = retrieve_chunks(
            user=self.owner,
            question="What is paging?",
            document_ids=[999],
            conversation_id=self.conversation.id,
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    @patch("apps.agent.pandu.tools.rag.answer_question")
    def test_ask_course_question_success(self, answer):
        answer.return_value = {
            "status": "ANSWERED",
            "answer": "Paging moves frames.",
            "citations": [],
        }

        result = ask_course_question(
            user=self.owner,
            conversation_id=self.conversation.id,
            question="What is paging?",
            document_ids=[3],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ANSWERED")
        self.assertEqual(result["answer"], "Paging moves frames.")
        self.assertEqual(result["citations"], [])
        answer.assert_called_once()

    @patch("apps.agent.pandu.tools.rag.answer_question")
    def test_ask_course_question_foreign_conversation(self, answer):
        result = ask_course_question(
            user=self.owner,
            conversation_id=self.other_conversation.id,
            question="What is paging?",
            document_ids=[3],
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
        answer.assert_not_called()

    @patch("apps.agent.pandu.tools.rag.answer_from_sources")
    @patch("apps.agent.pandu.tools.rag.retrieve_chunks_for_documents")
    @patch("apps.agent.pandu.tools.rag.answer_question", side_effect=RAGServiceError("boom"))
    def test_ask_course_question_falls_back_when_answer_question_fails(
        self, _answer, retrieve, from_sources
    ):
        retrieve.return_value = [
            {
                "chunk_id": 7,
                "document_id": 3,
                "page_number": 2,
                "content": "Paging moves frames.",
                "score": 0.91,
            }
        ]
        from_sources.return_value = {
            "ok": True,
            "status": "ANSWERED",
            "answer": "Paging moves frames.",
            "citations": [],
        }

        result = ask_course_question(
            user=self.owner,
            conversation_id=self.conversation.id,
            question="What is paging?",
            document_ids=[3],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ANSWERED")
        self.assertEqual(result["answer"], "Paging moves frames.")
        from_sources.assert_called_once()
        self.assertTrue(from_sources.call_args.kwargs.get("allow_uncited"))

    @patch("apps.agent.pandu.tools.rag.retrieve_chunks_for_documents", side_effect=Exception("down"))
    @patch("apps.agent.pandu.tools.rag.answer_question", side_effect=RAGServiceError("boom"))
    def test_ask_course_question_provider_failure(self, _answer, _retrieve):
        result = ask_course_question(
            user=self.owner,
            conversation_id=self.conversation.id,
            question="What is paging?",
            document_ids=[3],
        )
        self.assertEqual(result["code"], "RAG_GENERATION_FAILED")
        self.assertFalse(result["ok"])

    @patch("apps.agent.pandu.tools.rag.get_client")
    def test_answer_from_sources_uncited_allowed(self, get_client):
        get_client.return_value.generate.return_value = {
            "status": "ANSWERED",
            "answer": "Helpful uncited answer.",
            "citations": [
                {
                    "chunk_id": 1,
                    "document_id": 2,
                    "page_number": 1,
                    "excerpt": "not in source",
                }
            ],
        }

        with patch(
            "apps.agent.pandu.tools.rag.validate_answer",
            side_effect=InvalidCitation("bad citation"),
        ):
            result = answer_from_sources(
                user=self.owner,
                question="Explain paging",
                passages=[
                    {
                        "chunk_id": 1,
                        "document_id": 2,
                        "page": 1,
                        "text": "Paging moves frames between memory and disk.",
                    }
                ],
                allow_uncited=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ANSWERED")
        self.assertEqual(result["answer"], "Helpful uncited answer.")
        self.assertEqual(result["citations"], [])
        get_client.return_value.generate.assert_called_once()
        self.assertTrue(
            get_client.return_value.generate.call_args.kwargs.get("allow_uncited")
        )

    def test_ask_rejects_invalid_document_ids(self):
        result = ask_course_question(
            user=self.owner,
            conversation_id=self.conversation.id,
            question="What is paging?",
            document_ids=[1, 1],
        )
        self.assertEqual(result["code"], "INVALID_REQUEST")
