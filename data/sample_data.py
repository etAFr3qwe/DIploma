from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

import models
from scripts.generate_sample_handwritten_solutions import ensure_sample_handwritten_solutions


USERS = [
    {
        "name": "Никита Волков",
        "role": "Student",
        "email": "student@example.com",
        "password": "password",
        "grade": "9 класс",
        "target_exam": "ОГЭ",
        "goal": "первичная диагностика уровня подготовки",
    },
    {
        "name": "Алина Смирнова",
        "role": "Student",
        "email": "alina@example.com",
        "password": "password",
        "grade": "9 класс",
        "target_exam": "ОГЭ",
        "goal": "подготовка к ОГЭ",
    },
    {
        "name": "Борис Ковалёв",
        "role": "Student",
        "email": "boris@example.com",
        "password": "password",
        "grade": "9 класс",
        "target_exam": "ОГЭ",
        "goal": "подтянуть алгебру и научиться оформлять решения",
    },
    {
        "name": "Мария Орлова",
        "role": "Student",
        "email": "maria@example.com",
        "password": "password",
        "grade": "11 класс",
        "target_exam": "ЕГЭ",
        "goal": "подготовка к профильной математике",
    },
    {
        "name": "Дмитрий Соколов",
        "role": "Student",
        "email": "dmitry@example.com",
        "password": "password",
        "grade": "11 класс",
        "target_exam": "ЕГЭ",
        "goal": "стабилизировать результат по второй части",
    },
    {
        "name": "Ирина Петрова",
        "role": "Parent",
        "email": "parent@example.com",
        "password": "password",
        "grade": "-",
        "target_exam": "ОГЭ",
        "goal": "видеть реальную динамику подготовки ребёнка",
    },
    {
        "name": "Сергей Иванов",
        "role": "Teacher",
        "email": "teacher@example.com",
        "password": "password",
        "grade": "-",
        "target_exam": "ОГЭ",
        "goal": "проверка работ и сопровождение учеников",
    },
    {
        "name": "Администратор системы",
        "role": "Admin",
        "email": "admin@example.com",
        "password": "password",
        "grade": "-",
        "target_exam": "ОГЭ",
        "goal": "администрирование учебной системы",
    },
]


COURSES = [
    {
        "title": "Подготовка к ОГЭ по математике",
        "exam_type": "ОГЭ",
        "description": (
            "Курс выстроен по темам ОГЭ: вычисления, алгебра, функции, текстовые задачи, "
            "вероятность, геометрия и задания с развёрнутым решением."
        ),
        "format_with_teacher_price": 0,
        "format_ai_price": 0,
    },
    {
        "title": "Подготовка к ЕГЭ по математике",
        "exam_type": "ЕГЭ",
        "description": (
            "Курс охватывает профильную математику ЕГЭ: уравнения, неравенства, производную, "
            "тригонометрию, геометрию, финансовую математику и параметры."
        ),
        "format_with_teacher_price": 0,
        "format_ai_price": 0,
    },
]


PIPELINE_STEPS = [
    "Файл загружен",
    "Текст распознан",
    "Ответ извлечён",
    "Ответ сравнен с эталоном",
    "Решение проанализировано ИИ",
    "Ошибки зафиксированы",
    "Рекомендации сформированы",
]


def seed_sample_data(db: Session) -> None:
    """Create a clean initial dataset from imported PDF bank manifests."""
    _clear_learning_data(db)
    users = {item["email"]: _upsert_user(db, item) for item in USERS}
    db.flush()

    courses = [_create_course(db, data) for data in COURSES]
    db.flush()
    for course, exam_code in zip(courses, ["OGE", "EGE_PROFILE"], strict=True):
        _create_course_content_from_manifest(db, course, exam_code)
    db.flush()

    _create_boris_weekly_plan(db, users["boris@example.com"])
    db.flush()
    _create_boris_sample_attempts(db, users["boris@example.com"], users["teacher@example.com"])
    db.flush()
    _create_boris_chat_history(db, users["boris@example.com"])
    _create_boris_analytics(db, users["boris@example.com"])
    db.commit()


def _clear_learning_data(db: Session) -> None:
    for model in (
        models.TeacherComment,
        models.AIReview,
        models.CheckPipelineStep,
        models.ChatMessage,
        models.ChatSession,
        models.AttemptSolutionPage,
        models.Attempt,
        models.PoolTask,
        models.AssignmentPool,
        models.AnalyticsSnapshot,
        models.PurchaseRequest,
        models.TopicMaterial,
        models.Task,
        models.Topic,
        models.ExamSection,
        models.Course,
    ):
        db.query(model).delete(synchronize_session=False)
    db.flush()


def _upsert_user(db: Session, data: dict) -> models.User:
    user = db.query(models.User).filter(models.User.email == data["email"]).first()
    if user is None:
        user = models.User(**data)
        db.add(user)
    else:
        for key, value in data.items():
            setattr(user, key, value)
    return user


def _create_course(db: Session, data: dict) -> models.Course:
    course = models.Course(**data)
    db.add(course)
    return course


def _create_course_content_from_manifest(db: Session, course: models.Course, exam_code: str) -> None:
    manifest_path = _manifest_path(exam_code)
    if not manifest_path.exists():
        raise RuntimeError(
            f"Не найден manifest импортированного банка заданий: {manifest_path}. "
            "Запустите scripts/import_math_bank.py для PDF ОГЭ и ЕГЭ перед стартом приложения."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sections: dict[int, models.ExamSection] = {}
    topics: dict[tuple[int, str], models.Topic] = {}
    for item in manifest.get("tasks", []):
        task_number = int(item["task_number"])
        section = sections.get(task_number)
        if section is None:
            section = models.ExamSection(
                course_id=course.id,
                number=task_number,
                title=item["section_title"],
                description=f"{item['section_title']}. Задания импортированы из PDF-банка и показываются как изображения.",
                max_score=item["max_score"],
            )
            db.add(section)
            db.flush()
            sections[task_number] = section

        topic_key = (section.id, item["topic"])
        topic = topics.get(topic_key)
        if topic is None:
            topic = models.Topic(
                course_id=course.id,
                section_id=section.id,
                title=item["topic"],
                theory_content=(
                    f"Тема соответствует номеру {task_number} экзамена. "
                    "Условие задания отображается как изображение из импортированного PDF-банка."
                ),
                examples="Откройте изображение задания, решите его по таймеру и отправьте краткий ответ или файл решения.",
                difficulty=item["difficulty"],
            )
            db.add(topic)
            db.flush()
            db.add(
                models.TopicMaterial(
                    topic_id=topic.id,
                    title=f"Материал по теме «{item['topic']}»",
                    content=topic.theory_content,
                    examples=topic.examples,
                )
            )
            topics[topic_key] = topic

        db.add(
            models.Task(
                course_id=course.id,
                section_id=section.id,
                topic_id=topic.id,
                title=item["title"],
                condition_text=item["condition_text"],
                correct_answer=item.get("answer") or "",
                solution_explanation=item.get("solution") or "Решение или ответ берётся из импортированного банка при наличии.",
                solution_video_url=None,
                exam_type=exam_code,
                part=item["part"],
                task_number=item["task_number"],
                prototype_number=item.get("prototype_number"),
                analog_number=item.get("analog_number"),
                bank_topic=item["topic"],
                image_path=item.get("image_path"),
                context_image_path=item.get("context_image_path"),
                answer=item.get("answer"),
                solution=item.get("solution"),
                source_file=item.get("source_file"),
                source_page=item.get("source_page"),
                is_active=item.get("is_active", True),
                task_type=item["task_type"],
                answer_format=item["answer_format"],
                criteria=item["criteria"],
                difficulty=item["difficulty"],
                max_score=item["max_score"],
            )
        )


def _manifest_path(exam_code: str) -> Path:
    folder = "oge" if exam_code == "OGE" else "ege_profile"
    return Path("data") / "imported_banks" / folder / "manifest.json"


def _create_boris_weekly_plan(db: Session, boris: models.User) -> None:
    course = db.query(models.Course).filter(models.Course.exam_type == "ОГЭ").one()
    selected = [
        _task_by_number(db, course, 9),
        _task_by_number(db, course, 10),
        _task_by_number(db, course, 23),
        _task_by_number(db, course, 20),
        _task_by_number(db, course, 21),
    ]
    now = datetime.utcnow()
    pool = models.AssignmentPool(
        user_id=boris.id,
        course_id=course.id,
        title="План Бориса на неделю: алгебра, вероятность и геометрия",
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=6),
        deadline=now + timedelta(days=6),
        status="в работе",
    )
    db.add(pool)
    db.flush()
    statuses = ["зачтено", "требуется исправление", "нужна ручная проверка", "не начато", "не начато"]
    for task, status in zip(selected, statuses, strict=False):
        db.add(models.PoolTask(pool_id=pool.id, task_id=task.id, status=status))


def _create_boris_sample_attempts(db: Session, boris: models.User, teacher: models.User) -> None:
    files = ensure_sample_handwritten_solutions()
    pool_tasks = (
        db.query(models.PoolTask)
        .join(models.AssignmentPool)
        .filter(models.AssignmentPool.user_id == boris.id)
        .order_by(models.PoolTask.id.asc())
        .limit(3)
        .all()
    )
    specs = [
        {
            "duration": 11 * 60 + 35,
            "file_key": "equation",
            "recognized": "x^2 - 7x + 10 = 0; D = 9; x1 = 2; x2 = 5; ответ 2; 5",
            "extracted": "2; 5",
            "correct": True,
            "score": 1,
            "status": "зачтено",
            "review": "Решение полное: дискриминант найден верно, оба корня записаны в правильном порядке.",
            "mistakes": "",
            "recommendations": "Закрепить квадратные уравнения через 2 похожих примера и переходить к системам.",
            "quality": 94,
            "teacher_comment": "Работа зачтена. Оформление аккуратное, проверка корней понятна.",
            "teacher_status": "проверено преподавателем",
        },
        {
            "duration": 8 * 60 + 20,
            "file_key": "probability",
            "recognized": "7 синих и 5 зелёных. Всего 12. Ученик записал вероятность 7/12 вместо 5/12.",
            "extracted": "7/12",
            "correct": False,
            "score": 0,
            "status": "требуется исправление",
            "review": "Ход решения показывает понимание общего числа исходов, но выбран не тот благоприятный исход.",
            "mistakes": "Перепутаны благоприятные исходы: нужно выбрать зелёный карандаш, их 5, а не 7.",
            "recommendations": "Перед вычислением подчёркивать в условии, какое событие считается благоприятным.",
            "quality": 52,
            "teacher_comment": "",
            "teacher_status": "",
        },
        {
            "duration": 17 * 60 + 5,
            "file_key": "geometry",
            "recognized": "Есть чертёж прямоугольного треугольника, записано 9^2 + 12^2, итоговый ответ читается неуверенно.",
            "extracted": "",
            "correct": None,
            "score": None,
            "status": "нужна ручная проверка",
            "review": "Распознанный текст неполный: виден правильный подход через теорему Пифагора, но итоговый ответ извлечён неуверенно.",
            "mistakes": "Требуется ручная проверка преподавателя: часть записи на фото читается недостаточно чётко.",
            "recommendations": "Переснять работу ровнее или подписывать итоговый ответ отдельной строкой.",
            "quality": 68,
            "teacher_comment": "",
            "teacher_status": "",
        },
    ]
    started_base = datetime.utcnow() - timedelta(days=3)
    for index, (pool_task, spec) in enumerate(zip(pool_tasks, specs, strict=False), start=1):
        started_at = started_base + timedelta(days=index - 1, hours=1)
        committed_at = started_at + timedelta(seconds=spec["duration"])
        solution_file = files[spec["file_key"]]
        attempt = models.Attempt(
            user_id=boris.id,
            task_id=pool_task.task_id,
            pool_task_id=pool_task.id,
            attempt_number=1,
            started_at=started_at,
            committed_at=committed_at,
            duration_seconds=spec["duration"],
            uploaded_file_path=solution_file["path"],
            uploaded_file_name=solution_file["name"],
            student_text_answer="",
            recognized_text=spec["recognized"],
            extracted_answer=spec["extracted"],
            is_correct=spec["correct"],
            score=spec["score"],
            status=spec["status"],
        )
        db.add(attempt)
        db.flush()
        db.add(
            models.AttemptSolutionPage(
                attempt_id=attempt.id,
                file_path=solution_file["path"],
                page_order=1,
                original_filename=solution_file["name"],
                uploaded_at=committed_at,
            )
        )
        pool_task.status = spec["status"]
        _add_pipeline(db, attempt, spec["status"])
        db.add(
            models.AIReview(
                attempt_id=attempt.id,
                agent_name="SolutionReviewAgent",
                review_text=spec["review"],
                mistakes=spec["mistakes"],
                recommendations=spec["recommendations"],
                quality_score=spec["quality"],
            )
        )
        if spec["teacher_comment"]:
            db.add(
                models.TeacherComment(
                    attempt_id=attempt.id,
                    teacher_id=teacher.id,
                    comment_text=spec["teacher_comment"],
                    final_score=spec["score"],
                    status=spec["teacher_status"],
                )
            )


def _add_pipeline(db: Session, attempt: models.Attempt, final_status: str) -> None:
    for step in PIPELINE_STEPS:
        status = "success"
        message = "Этап выполнен."
        if final_status == "нужна ручная проверка" and step in {"Ответ извлечён", "Ответ сравнен с эталоном"}:
            status = "teacher_required"
            message = "Ответ извлечён неуверенно, работа передана преподавателю."
        if final_status == "требуется исправление" and step == "Ошибки зафиксированы":
            message = "Зафиксирована ошибка в выборе благоприятных исходов."
        db.add(
            models.CheckPipelineStep(
                attempt_id=attempt.id,
                step_name=step,
                status=status,
                message=message,
            )
        )


def _create_boris_chat_history(db: Session, boris: models.User) -> None:
    attempt = (
        db.query(models.Attempt)
        .filter(models.Attempt.user_id == boris.id)
        .order_by(models.Attempt.id.desc())
        .first()
    )
    if not attempt:
        return
    session = models.ChatSession(
        user_id=boris.id,
        course_id=attempt.task.course_id,
        topic_id=attempt.task.topic_id,
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        summary="Краткое содержание диалога: Борис уточнял, как оформить геометрическое решение и где отдельно записать ответ.",
    )
    db.add(session)
    db.flush()
    db.add_all(
        [
            models.ChatMessage(session_id=session.id, role="user", content="Я решил через теорему Пифагора, но не уверен, как оформить ответ."),
            models.ChatMessage(session_id=session.id, role="assistant", content="Запиши формулу, подставь катеты и отдельной строкой укажи найденную гипотенузу. Готовый ответ проверь по квадратам."),
            models.ChatMessage(session_id=session.id, role="user", content="Если фото плохо читается, работа всё равно уйдёт преподавателю?"),
            models.ChatMessage(session_id=session.id, role="assistant", content="Да, если ответ извлечён неуверенно, преподаватель увидит фото, распознанный текст и историю попытки."),
        ]
    )


def _create_boris_analytics(db: Session, boris: models.User) -> None:
    course = db.query(models.Course).filter(models.Course.exam_type == "ОГЭ").one()
    attempts = db.query(models.Attempt).filter(models.Attempt.user_id == boris.id).all()
    committed = [attempt for attempt in attempts if attempt.committed_at]
    correct = [attempt for attempt in committed if attempt.is_correct]
    average_time = sum((attempt.duration_seconds or 0) for attempt in committed) / len(committed) if committed else 0
    correct_percent = len(correct) / len(committed) * 100 if committed else 0
    db.add(
        models.AnalyticsSnapshot(
            user_id=boris.id,
            course_id=course.id,
            completion_percent=40,
            correct_percent=round(correct_percent, 1),
            average_time_seconds=round(average_time, 1),
            first_try_success_percent=round(correct_percent, 1),
            mastered_task_types_count=len(correct),
            predicted_primary_score=12.5,
            predicted_test_score=12.5,
            predicted_grade="3",
            risk_level="средний",
        )
    )



def _task_by_number(db: Session, course: models.Course, task_number: int) -> models.Task:
    task = (
        db.query(models.Task)
        .filter(models.Task.course_id == course.id)
        .filter(models.Task.task_number == task_number)
        .filter(models.Task.is_active.is_(True))
        .order_by(models.Task.part.asc(), models.Task.id.asc())
        .first()
    )
    if task is None:
        raise RuntimeError(f"Не найдено импортированное задание ОГЭ №{task_number}")
    return task
