import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agent.pandu.tools.registry import get_tool
from apps.agent.pandu.tools.tasks import complete_task, create_task, list_tasks
from apps.courses.models import Course, TodoItem


class TaskToolsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(email="task-owner@example.test")
        cls.other = user_model.objects.create_user(email="task-other@example.test")
        cls.course = Course.objects.create(owner=cls.owner, name="Task course")
        cls.other_course = Course.objects.create(owner=cls.other, name="Foreign course")
        cls.todo = TodoItem.objects.create(
            course=cls.course, title="Read chapter 1", due_date="2026-11-20"
        )
        cls.other_todo = TodoItem.objects.create(
            course=cls.other_course, title="Secret task"
        )

    def test_tools_registered(self):
        self.assertFalse(get_tool("list_tasks").mutates)
        self.assertTrue(get_tool("create_task").mutates)
        self.assertTrue(get_tool("complete_task").mutates)
        self.assertIsNone(get_tool("update_task"))
        self.assertIsNone(get_tool("delete_task"))

    def test_list_tasks_only_owned(self):
        result = list_tasks(user=self.owner)
        self.assertTrue(result["ok"])
        ids = {task["id"] for task in result["tasks"]}
        self.assertEqual(ids, {self.todo.id})
        self.assertNotIn(self.other_todo.id, ids)

    def test_list_tasks_foreign_course(self):
        result = list_tasks(user=self.owner, course_id=self.other_course.id)
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_create_task_on_owned_course(self):
        key = str(uuid.uuid4())
        result = create_task(
            user=self.owner,
            course_id=self.course.id,
            title="Finish lab",
            creation_key=key,
            due_date="2026-12-01",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertEqual(result["task"]["title"], "Finish lab")
        self.assertEqual(result["task"]["course_id"], self.course.id)

    def test_create_task_foreign_course(self):
        result = create_task(
            user=self.owner,
            course_id=self.other_course.id,
            title="Nope",
            creation_key=str(uuid.uuid4()),
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")

    def test_create_task_idempotent_retry(self):
        key = str(uuid.uuid4())
        first = create_task(
            user=self.owner,
            course_id=self.course.id,
            title="Same task",
            creation_key=key,
        )
        second = create_task(
            user=self.owner,
            course_id=self.course.id,
            title="Same task",
            creation_key=key,
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task"]["id"], second["task"]["id"])

    def test_create_task_conflict_on_key_reuse(self):
        key = str(uuid.uuid4())
        create_task(
            user=self.owner,
            course_id=self.course.id,
            title="Original",
            creation_key=key,
        )
        conflict = create_task(
            user=self.owner,
            course_id=self.course.id,
            title="Different",
            creation_key=key,
        )
        self.assertEqual(conflict["code"], "CONFLICT")

    def test_complete_task_owned(self):
        result = complete_task(user=self.owner, task_id=self.todo.id, is_completed=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["task"]["is_completed"])
        self.todo.refresh_from_db()
        self.assertTrue(self.todo.is_completed)

    def test_complete_task_foreign(self):
        result = complete_task(
            user=self.owner, task_id=self.other_todo.id, is_completed=True
        )
        self.assertEqual(result["code"], "RESOURCE_NOT_FOUND")
        self.other_todo.refresh_from_db()
        self.assertFalse(self.other_todo.is_completed)
