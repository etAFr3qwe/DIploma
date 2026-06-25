from __future__ import annotations

from sqlalchemy.orm import Session

import models
from services.ai_client import AIClient, AIClientFactory
from services.chat_memory import ChatMemoryService
from services.topic_guard import TopicGuardAgent


class TutorChatAgent:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("tutor_chat")
        self.memory = ChatMemoryService(self.ai_client)
        self.guard = TopicGuardAgent()

    def answer(
        self,
        db: Session,
        user_id: int,
        message: str,
        course_id: int | None = None,
        topic_id: int | None = None,
        task_id: int | None = None,
        attempt_id: int | None = None,
    ) -> dict:
        guard_result = self.guard.classify(message)
        session = self.memory.get_or_create_session(db, user_id, course_id, topic_id, task_id, attempt_id)
        dialog_summary, recent_messages, summary_used = self.memory.prepare_context(db, session)
        self.memory.add_message(db, session, "user", message)

        if not guard_result["allowed"]:
            answer = (
                f"{guard_result['reason']} Я помогу честно: объясню метод, разберу ошибку "
                "или дам похожее задание по математике."
            )
        else:
            fallback = self._local_answer(db, user_id, message, course_id, topic_id, task_id, guard_result)
            context = self._build_context(db, user_id, course_id, topic_id, task_id, dialog_summary, recent_messages)
            course = db.get(models.Course, course_id) if course_id else None
            topic = db.get(models.Topic, topic_id) if topic_id else None
            task = db.get(models.Task, task_id) if task_id else None
            answer = self.ai_client.chat_with_tutor(
                message,
                course=course,
                topic=topic,
                task=task,
                chat_history=[{"role": item.role, "content": item.content} for item in recent_messages],
                fallback=f"{fallback}\n\nКонтекст ученика:\n{context}",
            )

        self.memory.add_message(db, session, "assistant", answer)
        db.commit()
        return {
            "user_id": user_id,
            "session_id": session.id,
            "answer": answer,
            "allowed": guard_result["allowed"],
            "detected_topic": guard_result["detected_topic"],
            "summary_used": summary_used,
            "dialog_summary_used": summary_used,
            "recommendations": self._recommendations(db, user_id, course_id),
        }

    @staticmethod
    def _build_context(
        db: Session,
        user_id: int,
        course_id: int | None,
        topic_id: int | None,
        task_id: int | None,
        dialog_summary: str,
        recent_messages: list[models.ChatMessage],
    ) -> str:
        user = db.get(models.User, user_id)
        course = db.get(models.Course, course_id) if course_id else None
        topic = db.get(models.Topic, topic_id) if topic_id else None
        task = db.get(models.Task, task_id) if task_id else None
        material = topic.materials[0] if topic and topic.materials else task.topic.materials[0] if task and task.topic and task.topic.materials else None
        attempts = []
        if task:
            attempts = (
                db.query(models.Attempt)
                .filter(models.Attempt.user_id == user_id)
                .filter(models.Attempt.task_id == task.id)
                .order_by(models.Attempt.id.desc())
                .limit(3)
                .all()
            )
        recent_text = "\n".join(f"{item.role}: {item.content}" for item in recent_messages[-6:])
        attempt_text = "; ".join(
            f"попытка {item.attempt_number}: ответ {item.extracted_answer}, верно={item.is_correct}"
            for item in attempts
        )
        return (
            f"Ученик: {user.name if user else '-'}, класс: {user.grade if user else '-'}, цель: {user.goal if user else '-'}.\n"
            f"Курс: {course.title if course else '-'}.\n"
            f"Тема: {topic.title if topic else '-'}.\n"
            f"Материал темы: {material.title if material else '-'}\n"
            f"Краткое объяснение: {material.content if material else '-'}\n"
            f"Пример из материала: {material.examples if material else '-'}\n"
            f"Задание: {task.condition_text if task else '-'}\n"
            f"Критерии: {task.criteria if task else '-'}\n"
            f"Краткое содержание диалога: {dialog_summary or '-'}\n"
            f"Последние сообщения:\n{recent_text or '-'}\n"
            f"Предыдущие попытки: {attempt_text or '-'}"
        )

    @staticmethod
    def _local_answer(
        db: Session,
        user_id: int,
        message: str,
        course_id: int | None,
        topic_id: int | None,
        task_id: int | None,
        guard_result: dict,
    ) -> str:
        task = db.get(models.Task, task_id) if task_id else None
        topic = db.get(models.Topic, topic_id) if topic_id else (task.topic if task else None)
        material = topic.materials[0] if topic and topic.materials else None
        text = message.lower()
        if "ошиб" in text or "почему" in text:
            return (
                f"Сначала сравни свой ход решения с критерием: {task.criteria if task else 'метод, вычисления, проверка, ответ'}. "
                "Найди первый шаг, где результат перестал совпадать с условием. Пришли этот шаг, и я помогу его разобрать."
            )
        if "план" in text or "недел" in text:
            return (
                "План на неделю: решать по два задания в день по таймеру, каждую попытку отправлять в систему, "
                "после ошибки решать похожую задачу и в конце недели смотреть прогноз и слабые темы."
            )
        if "объяс" in text or "как" in text:
            return (
                f"По теме «{topic.title if topic else guard_result['detected_topic']}» действуй так: выпиши данные, "
                "определи тип задания, выбери формулу или метод, реши и обязательно проверь ответ. "
                f"В материале темы полезно повторить: {material.content if material else 'правило, пример и критерии оформления'}"
            )
        return (
            "Я помогу по шагам. Напиши, где именно остановился: выбор метода, вычисления, оформление или проверка ответа."
        )

    @staticmethod
    def _recommendations(db: Session, user_id: int, course_id: int | None) -> list[str]:
        query = db.query(models.Attempt).filter(models.Attempt.user_id == user_id)
        if course_id:
            query = query.join(models.Task).filter(models.Task.course_id == course_id)
        recent_wrong = query.filter(models.Attempt.is_correct.is_(False)).order_by(models.Attempt.id.desc()).limit(3).all()
        if recent_wrong:
            return [f"Повторить тему: {attempt.task.topic.title}" for attempt in recent_wrong]
        return ["Решить следующее задание из недельного плана", "Отправить попытку по таймеру"]
