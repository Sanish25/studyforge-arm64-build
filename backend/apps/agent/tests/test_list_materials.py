from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agent.pandu.tools import materials as materials_module
from apps.agent.pandu.tools.materials import list_materials
from apps.agent.pandu.tools.registry import get_tool
from apps.courses.models import Course
from apps.documents.models import Document


class ListMaterialsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="materials-owner@example.test")
        cls.other = user_model.objects.create_user(email="materials-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Owned course")
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
            title="Notes.pdf",
            sha256="b" * 64,
            file="documents/notes.pdf",
            status=Document.Status.PENDING,
        )
        Document.objects.create(
            owner=cls.other,
            course=cls.other_course,
            title="Secret.pdf",
            sha256="c" * 64,
            file="documents/secret.pdf",
            status=Document.Status.READY,
        )

    def test_tool_is_registered(self):
        spec = get_tool("list_materials")
        self.assertIsNotNone(spec)
        self.assertIs(spec.handler, materials_module.list_materials)
        self.assertFalse(spec.mutates)

    def test_lists_owned_course_materials(self):
        result = list_materials(user=self.owner, course_id=self.course.id)

        self.assertTrue(result["ok"])
        titles = [doc["title"] for doc in result["documents"]]
        self.assertEqual(titles, ["Notes.pdf", "Lecture.pdf"])
        self.assertEqual(
            {doc["id"] for doc in result["documents"]},
            {self.pending.id, self.ready.id},
        )
        self.assertTrue(all(doc["status"] in Document.Status.values for doc in result["documents"]))
        self.assertTrue(all("created_at" in doc for doc in result["documents"]))

    def test_foreign_course_is_not_found(self):
        result = list_materials(user=self.owner, course_id=self.other_course.id)

        self.assertEqual(
            result,
            {"ok": False, "code": "RESOURCE_NOT_FOUND", "message": "Resource not found."},
        )

    def test_missing_course_is_not_found(self):
        result = list_materials(user=self.owner, course_id=9_999_999)
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_invalid_course_id(self):
        result = list_materials(user=self.owner, course_id="abc")
        self.assertEqual(result["code"], "INVALID_REQUEST")
        self.assertFalse(result["ok"])
