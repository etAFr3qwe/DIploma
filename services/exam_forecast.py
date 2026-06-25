from __future__ import annotations

from collections import defaultdict

import numpy as np
from sklearn.metrics import accuracy_score, mean_squared_error, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

import models


class ExamForecastService:
    def analytics(self, db: Session, user_id: int, course_id: int | None = None) -> dict:
        user = db.get(models.User, user_id)
        if user is None:
            return {}
        course = self._resolve_course(db, user, course_id)
        attempts = self._attempts(db, user_id, course.id)
        tasks_count = db.query(models.Task).filter(models.Task.course_id == course.id).count() or 1
        completed_task_ids = {
            attempt.task_id
            for attempt in attempts
            if attempt.status in {"проверено", "проверено ИИ", "проверено преподавателем", "зачтено"}
        }
        correct_attempts = [attempt for attempt in attempts if attempt.is_correct]
        committed_attempts = [attempt for attempt in attempts if attempt.committed_at]

        completion = min(100.0, len(completed_task_ids) / tasks_count * 100)
        correct_percent = len(correct_attempts) / len(committed_attempts) * 100 if committed_attempts else 0.0
        avg_time = (
            sum((attempt.duration_seconds or 0) for attempt in committed_attempts) / len(committed_attempts)
            if committed_attempts
            else 0.0
        )
        first_try_percent = self._first_try_success(attempts)
        errors_by_topic = self._errors_by_topic(attempts)
        avg_by_type = self._average_time_by_type(committed_attempts)
        mastered = self._mastered_types(attempts)
        stability = self._stability(committed_attempts)
        forecast = self.forecast(db, user_id, course.id, save_snapshot=False)

        return {
            "user_id": user_id,
            "course_id": course.id,
            "completion_percent": round(completion, 1),
            "correct_percent": round(correct_percent, 1),
            "attempts_count": len(attempts),
            "average_time_seconds": round(avg_time, 1),
            "average_time_by_type": avg_by_type,
            "first_try_success_percent": round(first_try_percent, 1),
            "mastered_task_types_count": mastered,
            "stability_percent": round(stability, 1),
            "errors_by_topic": errors_by_topic,
            "predicted_primary_score": forecast["expected_primary_score"],
            "predicted_test_score": forecast["expected_test_score"],
            "predicted_grade": forecast["predicted_grade"],
            "risk_level": forecast["risk_level"],
            "risks": forecast["risks"],
        }

    def forecast(self, db: Session, user_id: int, course_id: int | None = None, save_snapshot: bool = True) -> dict:
        user = db.get(models.User, user_id)
        if user is None:
            return {}
        course = self._resolve_course(db, user, course_id)
        attempts = self._attempts(db, user_id, course.id)
        committed = [attempt for attempt in attempts if attempt.committed_at]
        correct = [attempt for attempt in committed if attempt.is_correct]
        sections = db.query(models.ExamSection).filter(models.ExamSection.course_id == course.id).all()
        covered_sections = {attempt.task.section_id for attempt in committed}

        coverage = len(covered_sections) / len(sections) if sections else 0
        correct_rate = len(correct) / len(committed) if committed else 0
        first_try = self._first_try_success(attempts) / 100
        stability = self._stability(committed) / 100
        speed_factor = self._speed_factor(committed)
        exam_multiplier = 31 if course.exam_type == "ОГЭ" else 32
        expected_primary = max(0, min(exam_multiplier, exam_multiplier * (0.36 * coverage + 0.34 * correct_rate + 0.15 * first_try + 0.15 * stability)))
        expected_test = expected_primary / exam_multiplier * (100 if course.exam_type == "ЕГЭ" else 31)
        if course.exam_type == "ОГЭ":
            grade = "5" if expected_primary >= 22 else "4" if expected_primary >= 15 else "3" if expected_primary >= 8 else "2"
        else:
            grade = "90+" if expected_test >= 90 else "75+" if expected_test >= 75 else "60+" if expected_test >= 60 else "ниже 60"
        weak_topics = self._weak_topics(attempts)
        strong_topics = self._strong_topics(attempts)
        risks = self._risks(coverage, correct_rate, speed_factor, weak_topics)
        risk_level = "низкий" if len(risks) <= 1 else "средний" if len(risks) <= 3 else "высокий"
        confidence = min(95.0, 45 + len(committed) * 3 + coverage * 20)

        result = {
            "user_id": user_id,
            "course_id": course.id,
            "expected_primary_score": round(expected_primary, 1),
            "expected_test_score": round(expected_test, 1),
            "predicted_grade": grade,
            "risk_level": risk_level,
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
            "weekly_focus": weak_topics[:3] or ["решать задания по таймеру", "оформлять проверку", "закрепить первую часть"],
            "confidence_percent": round(confidence, 1),
            "risks": risks,
        }
        if save_snapshot:
            self._save_snapshot(db, result, course.id, correct_rate, attempts)
        return result

    def parent_report(self, db: Session, user_id: int) -> dict:
        user = db.get(models.User, user_id)
        course = self._resolve_course(db, user, None)
        analytics = self.analytics(db, user_id, course.id)
        forecast = self.forecast(db, user_id, course.id, save_snapshot=False)
        attempts = self._attempts(db, user_id, course.id)
        return {
            "user_id": user_id,
            "student_name": user.name,
            "current_level": f"{user.grade}, цель: {user.goal}",
            "completed_tasks": len(
                {
                    attempt.task_id
                    for attempt in attempts
                    if attempt.status in {"проверено", "проверено ИИ", "проверено преподавателем", "зачтено"}
                }
            ),
            "attempts_count": len(attempts),
            "average_time_seconds": analytics["average_time_seconds"],
            "correct_percent": analytics["correct_percent"],
            "predicted_primary_score": forecast["expected_primary_score"],
            "predicted_test_score": forecast["expected_test_score"],
            "main_risks": forecast["risks"],
            "real_activity": [
                f"Сделано попыток: {len(attempts)}",
                f"Покрытие плана: {analytics['completion_percent']}%",
                f"Среднее время решения: {analytics['average_time_seconds']} сек.",
            ],
            "weak_topics": forecast["weak_topics"],
            "mastered_topics": forecast["strong_topics"],
            "next_week_recommendations": forecast["weekly_focus"],
        }

    def teacher_dashboard(self, db: Session) -> dict:
        students = db.query(models.User).filter(models.User.role == "Student").order_by(models.User.id).all()
        student_cards = []
        forecasts = []
        for student in students:
            forecast = self.forecast(db, student.id, save_snapshot=False)
            analytics = self.analytics(db, student.id, forecast["course_id"])
            student_cards.append(
                {
                    "id": student.id,
                    "name": student.name,
                    "grade": student.grade,
                    "target_exam": student.target_exam,
                    "progress": analytics["completion_percent"],
                    "correct_percent": analytics["correct_percent"],
                    "risk_level": forecast["risk_level"],
                }
            )
            forecasts.append({"student": student.name, **forecast})

        attempts_for_review = [
            self._attempt_card(attempt)
            for attempt in db.query(models.Attempt)
            .filter(models.Attempt.status.in_(["проверено", "проверено ИИ", "проверено преподавателем", "зачтено"]))
            .order_by(models.Attempt.id.desc())
            .limit(8)
        ]
        recent_attempts = [
            self._attempt_card(attempt)
            for attempt in db.query(models.Attempt).order_by(models.Attempt.id.desc()).limit(10)
        ]
        return {
            "students": student_cards,
            "attempts_for_review": attempts_for_review,
            "recent_attempts": recent_attempts,
            "forecasts": forecasts,
        }

    def train_quality_model(self, db: Session) -> dict:
        attempts = db.query(models.Attempt).filter(models.Attempt.is_correct.isnot(None)).all()
        if len(attempts) < 8:
            return {"samples": len(attempts), "accuracy": 0.0, "roc_auc": None, "test_loss": 0.0, "message": "Недостаточно попыток для оценки."}
        x = np.array(
            [
                [
                    attempt.duration_seconds or 0,
                    attempt.attempt_number,
                    attempt.task.max_score,
                    1 if attempt.task.difficulty == "повышенный" else 0,
                ]
                for attempt in attempts
            ],
            dtype=float,
        )
        y = np.array([1 if attempt.is_correct else 0 for attempt in attempts], dtype=int)
        x = StandardScaler().fit_transform(x)
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=42)
        # Lightweight deterministic linear score for the MVP; metrics use sklearn.
        weights = np.array([-0.25, -0.35, 0.25, -0.15])
        scores = 1 / (1 + np.exp(-(x_test @ weights)))
        pred = (scores >= 0.5).astype(int)
        try:
            auc = float(roc_auc_score(y_test, scores))
        except ValueError:
            auc = None
        return {
            "samples": len(attempts),
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "roc_auc": round(auc, 4) if auc is not None else None,
            "test_loss": round(float(mean_squared_error(y_test, scores)), 4),
            "message": "Прогнозная модель качества попыток оценена.",
        }

    @staticmethod
    def _resolve_course(db: Session, user: models.User, course_id: int | None) -> models.Course:
        if course_id:
            return db.get(models.Course, course_id)
        return db.query(models.Course).filter(models.Course.exam_type == user.target_exam).first() or db.query(models.Course).first()

    @staticmethod
    def _attempts(db: Session, user_id: int, course_id: int) -> list[models.Attempt]:
        return (
            db.query(models.Attempt)
            .join(models.Task)
            .filter(models.Attempt.user_id == user_id)
            .filter(models.Task.course_id == course_id)
            .order_by(models.Attempt.created_at.asc())
            .all()
        )

    @staticmethod
    def _first_try_success(attempts: list[models.Attempt]) -> float:
        by_task: dict[int, list[models.Attempt]] = defaultdict(list)
        for attempt in attempts:
            by_task[attempt.task_id].append(attempt)
        if not by_task:
            return 0.0
        successes = sum(1 for items in by_task.values() if sorted(items, key=lambda item: item.attempt_number)[0].is_correct)
        return successes / len(by_task) * 100

    @staticmethod
    def _errors_by_topic(attempts: list[models.Attempt]) -> dict[str, int]:
        errors: dict[str, int] = defaultdict(int)
        for attempt in attempts:
            if attempt.is_correct is False:
                errors[attempt.task.topic.title] += 1
        return dict(errors)

    @staticmethod
    def _average_time_by_type(attempts: list[models.Attempt]) -> dict[str, float]:
        buckets: dict[str, list[int]] = defaultdict(list)
        for attempt in attempts:
            buckets[attempt.task.section.title].append(attempt.duration_seconds or 0)
        return {key: round(sum(values) / len(values), 1) for key, values in buckets.items() if values}

    @staticmethod
    def _mastered_types(attempts: list[models.Attempt]) -> int:
        mastered = {
            attempt.task.section_id
            for attempt in attempts
            if attempt.is_correct and attempt.score and attempt.score >= attempt.task.max_score
        }
        return len(mastered)

    @staticmethod
    def _stability(attempts: list[models.Attempt]) -> float:
        recent = attempts[-8:]
        if not recent:
            return 0.0
        return sum(1 for attempt in recent if attempt.is_correct) / len(recent) * 100

    @staticmethod
    def _speed_factor(attempts: list[models.Attempt]) -> float:
        if not attempts:
            return 0.0
        avg = sum((attempt.duration_seconds or 0) for attempt in attempts) / len(attempts)
        return max(0.0, min(1.0, 1 - max(0, avg - 900) / 1800))

    def _weak_topics(self, attempts: list[models.Attempt]) -> list[str]:
        errors = self._errors_by_topic(attempts)
        return [topic for topic, _ in sorted(errors.items(), key=lambda item: item[1], reverse=True)[:5]]

    @staticmethod
    def _strong_topics(attempts: list[models.Attempt]) -> list[str]:
        successes: dict[str, int] = defaultdict(int)
        for attempt in attempts:
            if attempt.is_correct:
                successes[attempt.task.topic.title] += 1
        return [topic for topic, _ in sorted(successes.items(), key=lambda item: item[1], reverse=True)[:5]]

    @staticmethod
    def _risks(coverage: float, correct_rate: float, speed_factor: float, weak_topics: list[str]) -> list[str]:
        risks = []
        if coverage < 0.45:
            risks.append("низкое покрытие номеров экзамена")
        if correct_rate < 0.6:
            risks.append("много неверных ответов")
        if speed_factor < 0.45:
            risks.append("высокое время решения")
        if weak_topics:
            risks.append("есть повторяющиеся ошибки по темам")
        return risks or ["критичных рисков не видно"]

    @staticmethod
    def _save_snapshot(db: Session, result: dict, course_id: int, correct_rate: float, attempts: list[models.Attempt]) -> None:
        avg_time = sum((attempt.duration_seconds or 0) for attempt in attempts) / len(attempts) if attempts else 0
        db.add(
            models.AnalyticsSnapshot(
                user_id=result["user_id"],
                course_id=course_id,
                completion_percent=min(100, len({attempt.task_id for attempt in attempts}) * 4),
                correct_percent=round(correct_rate * 100, 1),
                average_time_seconds=round(avg_time, 1),
                first_try_success_percent=0,
                mastered_task_types_count=len(result["strong_topics"]),
                predicted_primary_score=result["expected_primary_score"],
                predicted_test_score=result["expected_test_score"],
                predicted_grade=result["predicted_grade"],
                risk_level=result["risk_level"],
            )
        )
        db.flush()

    @staticmethod
    def _attempt_card(attempt: models.Attempt) -> dict:
        return {
            "id": attempt.id,
            "student": attempt.user.name,
            "task": attempt.task.title,
            "topic": attempt.task.topic.title,
            "status": attempt.status,
            "score": attempt.score,
            "is_correct": attempt.is_correct,
            "duration_seconds": attempt.duration_seconds,
            "file_name": attempt.uploaded_file_name,
            "ai_comment": attempt.ai_reviews[-1].review_text if attempt.ai_reviews else "",
        }
