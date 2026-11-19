"""HTTP entry for the Pandu agent loop.

POST /api/v1/agent/pandu/
  JWT required → validate body → optional remember user turn → run_pandu_turn
  → optional remember assistant turn → JSON reply envelope.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework import exceptions
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.agent.pandu.loop import run_pandu_turn
from apps.agent.pandu.schema import error_reply
from apps.agent.pandu.tools.memory import remember_turn
from apps.agent.serializers import PanduAgentSerializer
from apps.conversations.models import ConversationMessage
from apps.conversations.services import mark_failed
from apps.documents.errors import error_body
from apps.identity.ownership import owned_conversation, owned_course


class PanduAgentView(APIView):
    """Student-facing agent turn. Tool calling stays on the backend."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = PanduAgentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "code": "INVALID_REQUEST",
                    "message": "Provide a valid Pandu agent request body.",
                    "details": serializer.errors,
                },
                status=400,
            )

        data = serializer.validated_data
        message = data["message"]
        course_id = data.get("course_id")
        conversation_id = data.get("conversation_id")
        document_ids = data.get("document_ids") or []

        # --- ownership checks before any LLM / DB memory write ---
        course = None
        if course_id is not None:
            course = owned_course(request.user, course_id)
            if course is None:
                return Response(error_body("RESOURCE_NOT_FOUND"), status=404)

        conversation = None
        if conversation_id is not None:
            conversation = owned_conversation(request.user, conversation_id)
            if conversation is None:
                return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
            # Course chat: conversation must match the course when both are sent.
            if course_id is not None and conversation.course_id not in (None, course_id):
                return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
            if course_id is None and conversation.course_id is not None:
                course_id = conversation.course_id
                course = owned_course(request.user, course_id)

        # course_name goes into the loop payload so "what course is this?" needs no extra tool.
        context = {
            "course_id": course_id,
            "course_name": course.name if course is not None else None,
            "conversation_id": conversation_id,
            "document_ids": document_ids,
        }

        # --- durable memory: save the student question first (SCRUM-24 pattern) ---
        question_id = None
        if conversation is not None:
            saved = remember_turn(
                user=request.user,
                conversation_id=conversation.id,
                role="user",
                content=message if message.strip() else "(empty message)",
            )
            if not saved.get("ok"):
                return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
            question_id = saved["id"]

        # Agent / Gemini work must not hold a request-wide DB transaction
        # (see urls.py: transaction.non_atomic_requests).
        try:
            reply = run_pandu_turn(user=request.user, message=message, context=context)
        except Exception:
            if question_id is not None:
                question = ConversationMessage.objects.filter(pk=question_id).first()
                if question is not None:
                    mark_failed(question)
            return Response(error_reply(), status=200)

        # --- durable memory: save Pandu's envelope as the assistant reply ---
        if question_id is not None:
            remembered = remember_turn(
                user=request.user,
                conversation_id=conversation.id,
                role="assistant",
                content=reply.get("text") or "",
                reply_to=question_id,
                status=ConversationMessage.Status.ANSWERED,
                citations=reply.get("citations") or [],
                tool_trace=reply.get("tool_trace") or [],
            )
            if not remembered.get("ok"):
                question = ConversationMessage.objects.filter(pk=question_id).first()
                if question is not None:
                    mark_failed(question)

        return Response(reply, status=200)

    def handle_exception(self, exc):
        if isinstance(exc, (exceptions.AuthenticationFailed, exceptions.NotAuthenticated)):
            return Response(
                error_body("AUTHENTICATION_REQUIRED"),
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if isinstance(exc, (Http404, exceptions.NotFound)):
            return Response(error_body("RESOURCE_NOT_FOUND"), status=404)
        if isinstance(exc, exceptions.ParseError):
            return Response(
                {"code": "INVALID_REQUEST", "message": "The request is malformed."},
                status=400,
            )
        return super().handle_exception(exc)
