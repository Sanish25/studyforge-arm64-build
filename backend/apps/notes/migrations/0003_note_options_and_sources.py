"""SCRUM-86: note options, and source documents stored as plain IDs.

The ManyToMany to documents.Document is replaced by NoteSource rows holding a
plain document_id (the SCRUM-98 pattern). Existing links are copied across
before the ManyToMany is dropped, and existing notes get the default options,
which describe how they were generated.
"""

import django.db.models.deletion
from django.db import migrations, models


def copy_links_to_sources(apps, schema_editor):
    CourseNotes = apps.get_model("notes", "CourseNotes")
    NoteSource = apps.get_model("notes", "NoteSource")
    Link = CourseNotes.source_documents.through

    by_notes = {}
    for notes_id, document_id in Link.objects.values_list("coursenotes_id", "document_id"):
        by_notes.setdefault(notes_id, []).append(document_id)

    # Upload order (primary key), the order generation gave them to the model.
    NoteSource.objects.bulk_create(
        NoteSource(notes_id=notes_id, document_id=document_id, position=position)
        for notes_id, document_ids in by_notes.items()
        for position, document_id in enumerate(sorted(document_ids))
    )


def copy_sources_to_links(apps, schema_editor):
    CourseNotes = apps.get_model("notes", "CourseNotes")
    Document = apps.get_model("documents", "Document")
    NoteSource = apps.get_model("notes", "NoteSource")
    Link = CourseNotes.source_documents.through

    # A plain id has no guarantee its document still exists; a foreign key does.
    existing = set(Document.objects.values_list("pk", flat=True))
    Link.objects.bulk_create(
        Link(coursenotes_id=notes_id, document_id=document_id)
        for notes_id, document_id in NoteSource.objects.values_list("notes_id", "document_id")
        if document_id in existing
    )


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_conversation_scope"),
        ("notes", "0002_course_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursenotes",
            name="note_type",
            field=models.CharField(
                choices=[("summary", "Summary"), ("outline", "Outline"), ("key_concepts", "Key concepts")],
                default="outline",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="coursenotes",
            name="detail_level",
            field=models.CharField(
                choices=[("brief", "Brief"), ("standard", "Standard"), ("detailed", "Detailed")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="coursenotes",
            name="format",
            field=models.CharField(
                choices=[("bullets", "Bullet points"), ("paragraphs", "Paragraphs")],
                default="bullets",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="coursenotes",
            constraint=models.CheckConstraint(
                condition=models.Q(("note_type__in", ["summary", "outline", "key_concepts"])),
                name="course_notes_note_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="coursenotes",
            constraint=models.CheckConstraint(
                condition=models.Q(("detail_level__in", ["brief", "standard", "detailed"])),
                name="course_notes_detail_level_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="coursenotes",
            constraint=models.CheckConstraint(
                condition=models.Q(("format__in", ["bullets", "paragraphs"])),
                name="course_notes_format_valid",
            ),
        ),
        migrations.CreateModel(
            name="NoteSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_id", models.PositiveBigIntegerField(db_index=True)),
                ("position", models.PositiveSmallIntegerField()),
                (
                    "notes",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sources",
                        to="notes.coursenotes",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("document_id__gt", 0)), name="note_source_document_positive"
                    ),
                    models.UniqueConstraint(fields=("notes", "document_id"), name="note_source_unique_document"),
                    models.UniqueConstraint(fields=("notes", "position"), name="note_source_unique_position"),
                ],
            },
        ),
        migrations.RunPython(copy_links_to_sources, copy_sources_to_links),
        migrations.RemoveField(
            model_name="coursenotes",
            name="source_documents",
        ),
    ]
