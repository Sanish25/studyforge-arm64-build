"""Remove private source files on direct and cascading document deletion."""

from django.db.models.signals import post_delete
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.courses.models import Course
from apps.documents.models import Document


@receiver(post_delete, sender=Document)
def delete_conversation_upload_file(sender, instance, **kwargs):
    if not instance.conversation_id or not instance.file.name:
        return
    try:
        instance.file.storage.delete(instance.file.name)
    except FileNotFoundError:
        pass


@receiver(pre_delete, sender=Course)
def capture_course_source_files(sender, instance, **kwargs):
    # Course deletion cascades documents before Course.post_delete runs, so
    # retain the storage handles and names while the rows still exist.
    instance._studyforge_document_files = [
        (document.file.storage, document.file.name)
        for document in Document.objects.filter(course=instance).only("file")
        if document.file.name
    ]


@receiver(post_delete, sender=Course)
def delete_course_source_files(sender, instance, **kwargs):
    for storage, name in getattr(instance, "_studyforge_document_files", []):
        try:
            storage.delete(name)
        except FileNotFoundError:
            pass
