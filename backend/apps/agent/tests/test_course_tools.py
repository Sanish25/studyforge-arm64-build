from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agent.pandu.tools.courses import list_courses
from apps.agent.pandu.tools.registry import get_tool
from apps.courses.models import Course


class CourseToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="courses-owner@example.test")
        cls.other = user_model.objects.create_user(email="courses-other@example.test")
        cls.biology = Course.objects.create(
            owner=cls.owner, name="Biology", description="Cells"
        )
        cls.os = Course.objects.create(
            owner=cls.owner, name="Operating Systems", description=""
        )
        cls.secret = Course.objects.create(
            owner=cls.other, name="Secret Course", description="Private"
        )

    def test_tool_registered(self):
        spec = get_tool("list_courses")
        self.assertIsNotNone(spec)
        self.assertFalse(spec.mutates)
        self.assertEqual(spec.parameters.get("properties"), {})

    def test_list_courses_only_owned(self):
        result = list_courses(user=self.owner)
        self.assertTrue(result["ok"])
        names = {course["name"] for course in result["courses"]}
        self.assertEqual(names, {"Biology", "Operating Systems"})
        self.assertNotIn(self.secret.id, {course["id"] for course in result["courses"]})
        # Newest first (os created after biology).
        self.assertEqual(result["courses"][0]["id"], self.os.id)
        self.assertEqual(result["courses"][0]["name"], "Operating Systems")
        self.assertEqual(result["courses"][1]["description"], "Cells")

    def test_list_courses_empty_for_user_without_courses(self):
        user_model = get_user_model()
        lonely = user_model.objects.create_user(email="courses-lonely@example.test")
        result = list_courses(user=lonely)
        self.assertTrue(result["ok"])
        self.assertEqual(result["courses"], [])
