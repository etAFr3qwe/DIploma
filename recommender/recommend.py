from __future__ import annotations

import warnings
from collections import defaultdict

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

import models


def recommend_next_tasks(db: Session, user_id: int, course_id: int | None = None, limit: int = 5) -> list[dict]:
    """Recommend tasks in the student's zone of proximal development."""
    user = db.get(models.User, user_id)
    if user is None:
        return []

    course = _resolve_course(db, user, course_id)
    if course is None:
        return []

    attempts = (
        db.query(models.Attempt)
        .join(models.Task)
        .filter(models.Attempt.user_id == user_id)
        .filter(models.Task.course_id == course.id)
        .all()
    )
    tasks = db.query(models.Task).filter(models.Task.course_id == course.id).order_by(models.Task.id.asc()).all()
    solved_task_ids = {attempt.task_id for attempt in attempts if attempt.is_correct is True}
    candidates = [task for task in tasks if task.id not in solved_task_ids] or tasks

    probabilities = _predict_success_probabilities(tasks, attempts, candidates)
    weak_topics = _weak_topic_counts(attempts)

    ranked = []
    for task in candidates:
        probability = probabilities.get(task.id, 0.55)
        weak_bonus = min(0.25, weak_topics.get(task.topic_id, 0) * 0.06)
        zone_score = 1 - abs(probability - 0.6)
        score = 0.7 * zone_score + weak_bonus
        ranked.append((score, probability, task))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "task_id": task.id,
            "title": task.title,
            "course_id": task.course_id,
            "course_title": task.course.title,
            "section": task.section.title,
            "topic": task.topic.title,
            "difficulty": task.difficulty,
            "success_probability": round(float(probability), 3),
            "recommendation": _recommendation_reason(task, probability, weak_topics.get(task.topic_id, 0)),
        }
        for _, probability, task in ranked[:limit]
    ]


def _predict_success_probabilities(
    tasks: list[models.Task],
    attempts: list[models.Attempt],
    candidates: list[models.Task],
) -> dict[int, float]:
    train_attempts = [attempt for attempt in attempts if attempt.is_correct is not None]
    if len(train_attempts) < 8 or len({attempt.is_correct for attempt in train_attempts}) < 2:
        return _fallback_probabilities(attempts, candidates)

    x_train = np.array([_features(attempt.task, attempts, attempt) for attempt in train_attempts], dtype=float)
    y_train = np.array([1 if attempt.is_correct else 0 for attempt in train_attempts], dtype=int)
    x_candidates = np.array([_features(task, attempts) for task in candidates], dtype=float)

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_candidates_scaled = scaler.transform(x_candidates)
    model = MLPClassifier(hidden_layer_sizes=(24, 12), max_iter=400, random_state=42)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        model.fit(x_train_scaled, y_train)
    scores = model.predict_proba(x_candidates_scaled)[:, 1]
    return {task.id: float(score) for task, score in zip(candidates, scores)}


def _fallback_probabilities(attempts: list[models.Attempt], candidates: list[models.Task]) -> dict[int, float]:
    topic_stats: dict[int, list[int]] = defaultdict(list)
    for attempt in attempts:
        if attempt.is_correct is not None:
            topic_stats[attempt.task.topic_id].append(1 if attempt.is_correct else 0)

    result = {}
    for task in candidates:
        topic_values = topic_stats.get(task.topic_id, [])
        topic_rate = sum(topic_values) / len(topic_values) if topic_values else 0.55
        difficulty_penalty = 0.12 if task.difficulty == "повышенный" else 0.0
        result[task.id] = min(0.9, max(0.2, topic_rate - difficulty_penalty))
    return result


def _features(task: models.Task, attempts: list[models.Attempt], current_attempt: models.Attempt | None = None) -> list[float]:
    topic_attempts = [attempt for attempt in attempts if attempt.task.topic_id == task.topic_id and attempt.is_correct is not None]
    section_attempts = [attempt for attempt in attempts if attempt.task.section_id == task.section_id and attempt.is_correct is not None]
    topic_rate = sum(1 for attempt in topic_attempts if attempt.is_correct) / len(topic_attempts) if topic_attempts else 0.5
    section_rate = sum(1 for attempt in section_attempts if attempt.is_correct) / len(section_attempts) if section_attempts else 0.5
    attempts_for_task = [attempt for attempt in attempts if attempt.task_id == task.id]
    avg_time = (
        sum((attempt.duration_seconds or 0) for attempt in attempts_for_task) / len(attempts_for_task)
        if attempts_for_task
        else 600
    )
    attempt_number = current_attempt.attempt_number if current_attempt else len(attempts_for_task) + 1
    return [
        task.section.number,
        task.max_score,
        1 if task.difficulty == "повышенный" else 0,
        topic_rate,
        section_rate,
        len(attempts_for_task),
        min(avg_time, 2400) / 2400,
        attempt_number,
    ]


def _weak_topic_counts(attempts: list[models.Attempt]) -> dict[int, int]:
    weak_topics: dict[int, int] = defaultdict(int)
    for attempt in attempts:
        if attempt.is_correct is False:
            weak_topics[attempt.task.topic_id] += 1
    return weak_topics


def _recommendation_reason(task: models.Task, probability: float, error_count: int) -> str:
    if error_count:
        return f"Тема «{task.topic.title}» требует повторения, вероятность успешного решения около {round(probability * 100)}%."
    if 0.5 <= probability <= 0.72:
        return "Задание находится в зоне ближайшего развития: достаточно сложное, но посильное."
    if probability < 0.5:
        return "Перед решением стоит открыть материал темы и разобрать пример."
    return "Подходит для закрепления устойчивого результата по теме."


def _resolve_course(db: Session, user: models.User, course_id: int | None) -> models.Course | None:
    if course_id:
        return db.get(models.Course, course_id)
    return db.query(models.Course).filter(models.Course.exam_type == user.target_exam).first()
