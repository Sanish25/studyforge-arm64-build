"""SCRUM-79 regression coverage for rename, delete, and document cleanup."""

import pytest
from django.core.files.base import ContentFile
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.documents.models import Document, Job
from apps.knowledge.models import Chunk
from apps.notes.models import CourseNotes, NoteSource, StudyGuide
from apps.quizzes.models import Quiz

pytestmark = pytest.mark.django_db(transaction=True)


def document_detail(document):
    return f"/api/v1/documents/{document.pk}/"


def test_rename_changes_only_display_name(owner_client, document_factory):
    document = document_factory(status=Document.Status.PROCESSING)
    before = {
        "status": document.status,
        "file": document.file.name,
        "sha256": document.sha256,
    }

    response = owner_client.patch(
        document_detail(document), {"name": "  Renamed material  "}, format="json"
    )

    assert response.status_code == 200
    document.refresh_from_db()
    assert response.json()["name"] == "Renamed material"
    assert document.title == "Renamed material"
    assert document.status == before["status"]
    assert document.file.name == before["file"]
    assert document.sha256 == before["sha256"]


def test_delete_removes_source_jobs_chunks_embeddings_guides_and_notes(
    owner_client, document_factory, owner
):
    document = document_factory(status=Document.Status.READY)
    job = Job.objects.create(document=document)
    chunk = Chunk.objects.create(
        owner=owner,
        document=document,
        page_number=1,
        content="Material text",
        embedding=[0.5] * 768,
    )
    guide = StudyGuide.objects.create(document=document, summary="Summary")
    notes = CourseNotes.objects.create(
        owner=owner,
        course=document.course,
        title="Combined notes",
        overview="Overview",
        sections=[],
    )
    NoteSource.objects.create(notes=notes, document_id=document.pk, position=0)
    storage, source_name = document.file.storage, document.file.name

    response = owner_client.delete(document_detail(document))

    assert response.status_code == 204
    assert not Document.objects.filter(pk=document.pk).exists()
    assert not Job.objects.filter(pk=job.pk).exists()
    assert not Chunk.objects.filter(pk=chunk.pk).exists()
    assert not StudyGuide.objects.filter(pk=guide.pk).exists()
    assert not CourseNotes.objects.filter(pk=notes.pk).exists()
    assert not storage.exists(source_name)


def test_foreign_user_cannot_rename_or_delete_material(document_factory, other_user):
    document = document_factory()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(other_user)}")

    rename = client.patch(document_detail(document), {"name": "Changed"}, format="json")
    delete = client.delete(document_detail(document))

    assert rename.status_code == 404
    assert delete.status_code == 404
    assert Document.objects.filter(pk=document.pk).exists()
    assert document.file.storage.exists(document.file.name)


def test_course_delete_removes_course_material_source_files(owner, course):
    material = Document(owner=owner, course=course, title="Material", sha256="d" * 64)
    material.file.save("course-material.pdf", ContentFile(b"course material"))
    storage, source_name = material.file.storage, material.file.name

    course.delete()

    assert not Document.objects.filter(pk=material.pk).exists()
    assert not storage.exists(source_name)
