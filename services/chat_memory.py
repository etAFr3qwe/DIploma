from __future__ import annotations

import os

from sqlalchemy.orm import Session

import models
from services.ai_client import AIClient, AIClientFactory


class ChatMemoryService:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("tutor_chat")
        self.char_limit = int(os.getenv("CHAT_SUMMARY_CHAR_LIMIT", "400000"))

    def get_or_create_session(
        self,
        db: Session,
        user_id: int,
        course_id: int | None = None,
        topic_id: int | None = None,
        task_id: int | None = None,
        attempt_id: int | None = None,
    ) -> models.ChatSession:
        query = (
            db.query(models.ChatSession)
            .filter(models.ChatSession.user_id == user_id)
            .filter(models.ChatSession.course_id == course_id)
            .filter(models.ChatSession.topic_id == topic_id)
            .filter(models.ChatSession.task_id == task_id)
        )
        if attempt_id is not None:
            query = query.filter(models.ChatSession.attempt_id == attempt_id)
        session = query.order_by(models.ChatSession.id.desc()).first()
        if session is None:
            session = models.ChatSession(
                user_id=user_id,
                course_id=course_id,
                topic_id=topic_id,
                task_id=task_id,
                attempt_id=attempt_id,
            )
            db.add(session)
            db.flush()
        return session

    def add_message(self, db: Session, session: models.ChatSession, role: str, content: str) -> models.ChatMessage:
        message = models.ChatMessage(session_id=session.id, role=role, content=content)
        db.add(message)
        db.flush()
        return message

    def prepare_context(self, db: Session, session: models.ChatSession) -> tuple[str, list[models.ChatMessage], bool]:
        messages = session.messages
        history_text = "\n".join(f"{item.role}: {item.content}" for item in messages)
        summary_used = bool(session.summary)
        if len(history_text) > self.char_limit:
            fallback = self._local_summary(history_text)
            session.summary = self.ai_client.summarize(history_text[-self.char_limit:], fallback)
            messages = messages[-8:]
            summary_used = True
            db.flush()
        return session.summary, messages[-8:], summary_used

    @staticmethod
    def _local_summary(history_text: str) -> str:
        return (
            "Краткое содержание диалога: ученик готовится к ОГЭ/ЕГЭ по математике, задаёт вопросы по текущим заданиям, "
            "важно сохранять честное решение, проверять ход рассуждений и предлагать похожие задачи для закрепления."
        )
