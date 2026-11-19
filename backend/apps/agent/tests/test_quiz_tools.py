from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from apps.agent.pandu.tools.quizzes import generate_quiz_tool, get_quiz
from apps.agent.pandu.tools.registry import get_tool
from apps.courses.models import Course
from apps.documents.models import Document
from apps.quizzes.llm import LLMError
from apps.quizzes.models import Question, Quiz
from apps.quizzes.services import EmptyDocumentError


class QuizToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="quiz-owner@example.test")
        cls.other = user_model.objects.create_user(email="quiz-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Quiz course")
        cls.other_course = Course.objects.create(owner=cls.other, name="Foreign course")
        cls.ready = Document.objects.create(
            owner=cls.owner,
            course=cls.course,
            title="Lecture.pdf",
            sha256="a" * 64,
            file="documents/lecture.pdf",
            status=Document.Status.READY,
        )
        cls.pending = Document.objects.create(
            owner=cls.owner,
            course=cls.course,
            title="Pending.pdf",
            sha256="b" * 64,
            file="documents/pending.pdf",
            status=Document.Status.PENDING,
        )
        cls.quiz = Quiz.objects.create(
            owner=cls.owner, course=cls.course, title="Quiz: Lecture.pdf"
        )
        cls.quiz.source_documents.set([cls.ready])
        Question.objects.create(
            quiz=cls.quiz,
            position=1,
            text="What is paging?",
            options=["A", "B", "C", "D"],
            correct_option_index=0,
            explanation="Because frames move.",
        )
        cls.other_quiz = Quiz.objects.create(
            owner=cls.other, course=cls.other_course, title="Secret quiz"
        )

    def test_tools_registered(self):
        self.assertTrue(get_tool("generate_quiz").mutates)
        self.assertFalse(get_tool("get_quiz").mutates)

    @patch("apps.agent.pandu.tools.quizzes.generate_quiz")
    def test_generate_quiz_success(self, generate):
        generate.return_value = self.quiz

        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=5,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["quiz"]["id"], self.quiz.id)
        self.assertEqual(result["quiz"]["questions"][0]["text"], "What is paging?")
        self.assertNotIn("correct_option_index", result["quiz"]["questions"][0])
        generate.assert_called_once()

    @patch("apps.agent.pandu.tools.quizzes.generate_quiz")
    def test_generate_quiz_allows_multiple_calls(self, generate):
        second = Quiz.objects.create(
            owner=self.owner, course=self.course, title="Quiz: Lecture.pdf (2)"
        )
        generate.side_effect = [self.quiz, second]

        first = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=5,
        )
        again = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=10,
        )

        self.assertTrue(first["ok"])
        self.assertTrue(again["ok"])
        self.assertNotEqual(first["quiz"]["id"], again["quiz"]["id"])
        self.assertEqual(generate.call_count, 2)

    def test_generate_quiz_foreign_course(self):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.other_course.id,
            document_ids=[self.ready.id],
            num_questions=5,
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_generate_quiz_not_ready(self):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.pending.id],
            num_questions=5,
        )
        self.assertEqual(result["code"], "DOCUMENT_NOT_READY")

    def test_generate_quiz_invalid_num_questions(self):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=7,
        )
        self.assertEqual(result["code"], "INVALID_REQUEST")

    @patch(
        "apps.agent.pandu.tools.quizzes.generate_quiz",
        side_effect=EmptyDocumentError([1]),
    )
    def test_generate_quiz_empty_documents(self, _generate):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=5,
        )
        self.assertEqual(result["code"], "DOCUMENT_HAS_NO_TEXT")

    @patch("apps.agent.pandu.tools.quizzes.generate_quiz", side_effect=LLMError("down"))
    def test_generate_quiz_llm_failure(self, _generate):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
            num_questions=5,
        )
        self.assertEqual(result["code"], "QUIZ_GENERATION_FAILED")

    def test_get_quiz_success(self):
        result = get_quiz(user=self.owner, quiz_id=self.quiz.id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["quiz"]["id"], self.quiz.id)
        self.assertFalse(result["quiz"]["is_submitted"])

    def test_get_quiz_foreign(self):
        result = get_quiz(user=self.owner, quiz_id=self.other_quiz.id)
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    @patch("apps.agent.pandu.tools.quizzes.get_owned_course_documents", side_effect=Http404)
    def test_generate_missing_documents(self, _docs):
        result = generate_quiz_tool(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[9_999_999],
            num_questions=5,
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
