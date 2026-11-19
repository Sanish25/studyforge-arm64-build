from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from apps.agent.pandu.tools.notes import generate_notes, get_notes
from apps.agent.pandu.tools.registry import get_tool
from apps.courses.models import Course
from apps.documents.models import Document
from apps.notes.llm import LLMError
from apps.notes.models import CourseNotes, NoteSource
from apps.notes.services import EmptyMaterialsError, NotesInputTooLargeError


class NotesToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="notes-owner@example.test")
        cls.other = user_model.objects.create_user(email="notes-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Notes course")
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
        cls.notes = CourseNotes.objects.create(
            owner=cls.owner,
            course=cls.course,
            title="Notes: Lecture.pdf",
            overview="Overview text",
            sections=[],
        )
        NoteSource.objects.create(notes=cls.notes, document_id=cls.ready.id, position=0)
        cls.other_notes = CourseNotes.objects.create(
            owner=cls.other,
            course=cls.other_course,
            title="Secret notes",
            overview="Secret",
            sections=[],
        )

    def test_tools_registered(self):
        self.assertTrue(get_tool("generate_notes").mutates)
        self.assertFalse(get_tool("get_notes").mutates)

    @patch("apps.agent.pandu.tools.notes.generate_course_notes")
    def test_generate_notes_success(self, generate):
        generate.return_value = self.notes

        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["notes"]["id"], self.notes.id)
        self.assertEqual(result["notes"]["title"], self.notes.title)
        generate.assert_called_once()

    def test_generate_notes_foreign_course(self):
        result = generate_notes(
            user=self.owner,
            course_id=self.other_course.id,
            document_ids=[self.ready.id],
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_generate_notes_not_ready(self):
        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.pending.id],
        )
        self.assertEqual(result["code"], "DOCUMENT_NOT_READY")

    @patch("apps.agent.pandu.tools.notes.generate_course_notes", side_effect=EmptyMaterialsError([1]))
    def test_generate_notes_empty_materials(self, _generate):
        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
        )
        self.assertEqual(result["code"], "DOCUMENT_HAS_NO_TEXT")

    @patch(
        "apps.agent.pandu.tools.notes.generate_course_notes",
        side_effect=NotesInputTooLargeError(),
    )
    def test_generate_notes_too_large(self, _generate):
        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
        )
        self.assertEqual(result["code"], "NOTES_INPUT_TOO_LARGE")

    @patch("apps.agent.pandu.tools.notes.generate_course_notes", side_effect=LLMError("down"))
    def test_generate_notes_llm_failure(self, _generate):
        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[self.ready.id],
        )
        self.assertEqual(result["code"], "NOTES_GENERATION_FAILED")

    def test_get_notes_success(self):
        result = get_notes(user=self.owner, note_id=self.notes.id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["notes"]["id"], self.notes.id)
        self.assertEqual(result["notes"]["overview"], "Overview text")

    def test_get_notes_foreign(self):
        result = get_notes(user=self.owner, note_id=self.other_notes.id)
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    @patch("apps.agent.pandu.tools.notes.get_owned_course_documents", side_effect=Http404)
    def test_generate_missing_documents(self, _docs):
        result = generate_notes(
            user=self.owner,
            course_id=self.course.id,
            document_ids=[9_999_999],
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
