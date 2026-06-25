from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import models
import schemas
from data.sample_data import seed_sample_data
from database import SessionLocal, ensure_database_schema, get_db
from recommender.recommend import recommend_next_tasks
from services.ai_client import AIClientFactory
from services.exam_forecast import ExamForecastService
from services.solution_review import SolutionReviewAgent
from services.task_generator import TaskGeneratorAgent
from services.topic_guard import TopicGuardAgent
from services.tutor_chat import TutorChatAgent


UPLOAD_DIR = Path("uploads")
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_SOLUTION_PAGES = 10
MAX_UPLOAD_FILE_SIZE = 10 * 1024 * 1024
EXAM_COURSE_TITLES = {
    "Подготовка к ОГЭ по математике",
    "Подготовка к ЕГЭ по математике",
}

app = FastAPI(
    title="API платформы подготовки к экзаменам",
    description="Платформа подготовки к ОГЭ и ЕГЭ по математике с ИИ-проверкой, аналитикой и прогнозом результата.",
    version="3.0.0",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["duration"] = lambda value: _format_seconds(value)
templates.env.filters["datetime_ru"] = lambda value: _format_datetime(value)

forecast_service = ExamForecastService()
review_agent = SolutionReviewAgent()
tutor_agent = TutorChatAgent()
topic_guard = TopicGuardAgent()
task_generator = TaskGeneratorAgent()


@app.on_event("startup")
def on_startup() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    ensure_database_schema()
    db = SessionLocal()
    try:
        seed_sample_data(db)
    finally:
        db.close()


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/login")
def login_page(request: Request):
    return _message_response(
        request,
        title="Вход в учебный режим",
        message="Выберите тестового пользователя на главной странице и нажмите «Войти», чтобы открыть разделы по роли.",
        label="Доступ",
        active_page="login",
        primary_href=str(request.url_for("index")),
        primary_text="На главную",
    )


@app.get("/student/plan")
def student_plan_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"student", "admin"}:
        return _forbidden_page(request, "Этот раздел доступен только ученику.")
    course = _course_for_user(db, user)
    return RedirectResponse(url=f"/courses/{course.id}?user_id={user.id}#weekly-plan", status_code=303)


@app.get("/student/analytics")
def student_analytics_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"student", "admin"}:
        return _forbidden_page(request, "Этот раздел доступен только ученику.")
    course = _course_for_user(db, user)
    return RedirectResponse(url=f"/courses/{course.id}?user_id={user.id}#analytics", status_code=303)


@app.get("/student/forecast")
def student_forecast_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"student", "admin"}:
        return _forbidden_page(request, "Этот раздел доступен только ученику.")
    course = _course_for_user(db, user)
    return RedirectResponse(url=f"/courses/{course.id}?user_id={user.id}#forecast", status_code=303)


@app.get("/analytics")
def analytics_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    return student_analytics_page(request, user_id, db)


@app.get("/tutor")
def tutor_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"student", "admin"}:
        return _forbidden_page(request, "ИИ-тьютор доступен ученику или администратору.")
    course = _course_for_user(db, user)
    return RedirectResponse(url=f"/courses/{course.id}?user_id={user.id}#tutor", status_code=303)


@app.get("/teacher")
def teacher_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"teacher", "admin"}:
        return _forbidden_page(request, "Этот раздел доступен только преподавателю.")
    dashboard = get_teacher_dashboard(db)
    attempts_count = db.query(models.Attempt).filter(models.Attempt.committed_at.isnot(None)).count()
    return templates.TemplateResponse(
        request=request,
        name="teacher_dashboard.html",
        context={
            "current_user": user,
            "dashboard": dashboard,
            "attempts_count": attempts_count,
            "active_page": "teacher",
        },
    )


@app.get("/parent")
def parent_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    return parent_report_page(request, user_id, db)


@app.get("/parent/report")
def parent_report_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"parent", "admin"}:
        return _forbidden_page(request, "Этот раздел доступен только родителю.")
    child = _child_for_parent(db, user)
    if child is None:
        return _message_response(
            request,
            title="Родительский отчёт",
            message="Отчёт появится после добавления ученика и выполнения первых заданий.",
            label="Родительский доступ",
            active_page="parent_report",
            status_code=200,
        )
    report = forecast_service.parent_report(db, child.id)
    attempts = _user_attempts(db, child.id, limit=5)
    return templates.TemplateResponse(
        request=request,
        name="parent_report.html",
        context={
            "current_user": user,
            "child": child,
            "report": report,
            "recent_attempts": attempts,
            "active_page": "admin_parent_reports" if _role_key(user) == "admin" else "parent_report",
        },
    )


@app.get("/parent/progress")
def parent_progress_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) not in {"parent", "admin"}:
        return _forbidden_page(request, "Прогресс ребёнка доступен только родителю.")
    child = _child_for_parent(db, user)
    if child is None:
        return _message_response(
            request,
            title="Прогресс ребёнка",
            message="Данные появятся после выполнения первых заданий.",
            label="Родительский доступ",
            active_page="parent_progress",
            status_code=200,
        )
    attempts = _user_attempts(db, child.id, limit=40)
    report = forecast_service.parent_report(db, child.id)
    return templates.TemplateResponse(
        request=request,
        name="parent_progress.html",
        context={
            "current_user": user,
            "child": child,
            "report": report,
            "attempts": attempts,
            "active_page": "parent_progress",
        },
    )


@app.get("/admin")
def admin_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) != "admin":
        return _forbidden_page(request, "Этот раздел доступен только администратору.")
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={"current_user": user, "stats": _admin_stats(db), "active_page": "admin_analytics"},
    )


@app.get("/admin/users")
def admin_users_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) != "admin":
        return _forbidden_page(request, "Список пользователей доступен только администратору.")
    users = db.query(models.User).order_by(models.User.role.asc(), models.User.id.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={"current_user": user, "users": users, "active_page": "admin_users"},
    )


@app.get("/admin/courses")
def admin_courses_page(request: Request, user_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    user = _resolve_session_user_or_login(request, db, user_id)
    if not isinstance(user, models.User):
        return user
    if _role_key(user) != "admin":
        return _forbidden_page(request, "Управление курсами доступно только администратору.")
    return RedirectResponse(url=f"/courses?user_id={user.id}", status_code=303)


@app.get("/health", response_model=schemas.HealthResponse)
def health_check() -> schemas.HealthResponse:
    return schemas.HealthResponse(
        status="ok",
        message="Платформа подготовки к экзаменам работает. Главная страница доступна на /.",
    )


@app.get("/api/ai/health")
def ai_health_check() -> dict:
    return AIClientFactory.health()


@app.get("/courses")
def list_courses(
    request: Request,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if _wants_html(request):
        return templates.TemplateResponse(request=request, name="courses.html")
    courses = (
        db.query(models.Course)
        .filter(models.Course.title.in_(EXAM_COURSE_TITLES))
        .order_by(models.Course.id.asc())
        .all()
    )
    courses = sorted(courses, key=lambda course: 0 if course.exam_type == "ОГЭ" else 1)
    return [_course_to_read(db, course, user_id) for course in courses]


@app.get("/courses/{course_id}")
def get_course(
    course_id: int,
    request: Request,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    course = _get_course_or_404(db, course_id)
    if _wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="course.html",
            context={"course_id": course_id, "course_title": course.title},
        )
    return _course_detail_to_read(db, course, user_id)


@app.get("/courses/{course_id}/plan")
def get_course_plan(
    course_id: int,
    request: Request,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    course = _get_course_or_404(db, course_id)
    if _wants_html(request):
        suffix = f"?user_id={user_id}" if user_id else ""
        return RedirectResponse(url=f"/courses/{course.id}{suffix}#weekly-plan", status_code=303)
    if user_id is None:
        return []
    _get_user_or_404(db, user_id)
    pools = (
        db.query(models.AssignmentPool)
        .filter(models.AssignmentPool.user_id == user_id)
        .filter(models.AssignmentPool.course_id == course.id)
        .order_by(models.AssignmentPool.deadline.asc())
        .all()
    )
    return [_pool_to_read(pool, db=db) for pool in pools]


@app.get("/courses/{course_id}/sections", response_model=List[schemas.ExamSectionRead])
def get_course_sections(
    course_id: int,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    course = _get_course_or_404(db, course_id)
    return [_section_to_read(section, db=db, user_id=user_id) for section in course.sections]


@app.get("/courses/{course_id}/sections/{section_id}")
def get_course_section(
    course_id: int,
    section_id: int,
    request: Request,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    course = _get_course_or_404(db, course_id)
    section = _get_section_or_404(db, section_id)
    if section.course_id != course.id:
        raise HTTPException(status_code=404, detail="Модуль не относится к выбранному курсу")
    if _wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="section.html",
            context={"course_id": course_id, "section_id": section_id, "course_title": course.title, "section_title": section.title},
        )
    return _section_detail_to_read(db, section, user_id)


@app.get("/sections/{section_id}/topics", response_model=List[schemas.TopicRead])
def get_section_topics(
    section_id: int,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    section = _get_section_or_404(db, section_id)
    return [_topic_to_read(topic, db=db, user_id=user_id) for topic in section.topics]


@app.get("/topics/{topic_id}")
def get_topic(topic_id: int, user_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    topic = _get_topic_or_404(db, topic_id)
    data = _topic_to_read(topic, db=db, user_id=user_id)
    data["tasks"] = [_task_to_read(task, db=db, user_id=user_id) for task in topic.tasks]
    data["section"] = _section_to_read(topic.section, db=db, user_id=user_id)
    data["course"] = _course_to_read(db, topic.course, user_id)
    return data


@app.get("/topics/{topic_id}/material", response_model=schemas.TopicMaterialRead)
def get_topic_material(topic_id: int, db: Session = Depends(get_db)) -> dict:
    topic = _get_topic_or_404(db, topic_id)
    material = _primary_topic_material(topic)
    if not material:
        raise HTTPException(status_code=404, detail="Материал по теме не найден")
    return _topic_material_to_read(material)


@app.get("/topics/{topic_id}/tasks", response_model=List[schemas.TaskRead])
def get_topic_tasks(topic_id: int, user_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> list[dict]:
    topic = _get_topic_or_404(db, topic_id)
    return [_task_to_read(task, db=db, user_id=user_id) for task in topic.tasks]


@app.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    request: Request,
    user_id: int | None = Query(default=None),
    include_answer: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    task = _get_task_or_404(db, task_id)
    if _wants_html(request):
        task_image_url = _static_asset_url(task.image_path)
        task_context_image_url = _static_asset_url(task.context_image_path)
        return templates.TemplateResponse(
            request=request,
            name="task.html",
            context={
                "task_id": task_id,
                "task_title": task.title,
                "task_image_url": task_image_url,
                "task_context_image_url": task_context_image_url,
                "task_condition_text": "" if task_image_url else task.condition_text,
            },
        )
    data = _task_to_read(task, db=db, user_id=user_id)
    data["topic"] = _topic_to_read(task.topic, db=db, user_id=user_id)
    data["section"] = _section_to_read(task.section, db=db, user_id=user_id)
    data["course"] = _course_to_read(db, task.course, user_id)
    if not include_answer:
        data["correct_answer"] = None
        data["answer"] = None
        data["solution"] = None
        data["solution_explanation"] = ""
    return data


@app.get("/users", response_model=List[schemas.UserRead])
def list_users(role: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[models.User]:
    query = db.query(models.User)
    if role:
        query = query.filter(models.User.role == role)
    return query.order_by(models.User.id.asc()).all()


@app.post("/users", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)) -> models.User:
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    db_user = models.User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users/{user_id}/dashboard")
def get_user_dashboard(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _get_user_or_404(db, user_id)
    course = _course_for_user(db, user)
    pools = [_pool_to_read(pool, db=db) for pool in _user_pools(db, user_id)]
    attempts = [_attempt_to_read(attempt) for attempt in _user_attempts(db, user_id, limit=8)]
    analytics = forecast_service.analytics(db, user_id, course.id)
    forecast = forecast_service.forecast(db, user_id, course.id, save_snapshot=False)
    return {
        "user": schemas.UserRead.model_validate(user).model_dump(mode="json"),
        "role": user.role,
        "course": _course_to_read(db, course, user_id),
        "assignment_pools": pools,
        "recent_attempts": attempts,
        "analytics": analytics,
        "forecast": forecast,
    }


@app.get("/users/{user_id}/assignment-pools", response_model=List[schemas.AssignmentPoolRead])
def get_assignment_pools(user_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _get_user_or_404(db, user_id)
    return [_pool_to_read(pool, db=db) for pool in _user_pools(db, user_id)]


@app.post("/users/{user_id}/assignment-pools", response_model=schemas.AssignmentPoolRead, status_code=status.HTTP_201_CREATED)
def create_assignment_pool(user_id: int, payload: schemas.AssignmentPoolCreate, db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, user_id)
    course = _get_course_or_404(db, payload.course_id)
    now = datetime.utcnow()
    period_days = {"день": 1, "неделя": 7, "месяц": 30}[payload.period]
    pool = models.AssignmentPool(
        user_id=user_id,
        course_id=course.id,
        title=payload.title,
        period_start=now,
        period_end=now + timedelta(days=period_days),
        deadline=payload.deadline or now + timedelta(days=period_days),
        status="не начато",
    )
    db.add(pool)
    db.flush()
    task_ids = payload.task_ids
    if not task_ids:
        task_ids = [task.id for task in db.query(models.Task).filter(models.Task.course_id == course.id).order_by(models.Task.id).limit(6)]
    for task_id in task_ids:
        _get_task_or_404(db, task_id)
        db.add(models.PoolTask(pool_id=pool.id, task_id=task_id, status="не начато"))
    db.commit()
    db.refresh(pool)
    return _pool_to_read(pool, db=db)


@app.get("/assignment-pools/{pool_id}", response_model=schemas.AssignmentPoolRead)
def get_assignment_pool(pool_id: int, db: Session = Depends(get_db)) -> dict:
    pool = _get_pool_or_404(db, pool_id)
    return _pool_to_read(pool, db=db)


@app.post("/tasks/{task_id}/start", status_code=status.HTTP_201_CREATED)
def start_task_attempt(task_id: int, payload: schemas.AttemptStartRequest, db: Session = Depends(get_db)) -> dict:
    user = _get_user_or_404(db, payload.user_id)
    task = _get_task_or_404(db, task_id)
    pool_task = db.get(models.PoolTask, payload.pool_task_id) if payload.pool_task_id else None
    attempt_number = (
        db.query(models.Attempt)
        .filter(models.Attempt.user_id == user.id)
        .filter(models.Attempt.task_id == task.id)
        .count()
        + 1
    )
    attempt = models.Attempt(
        user_id=user.id,
        task_id=task.id,
        pool_task_id=pool_task.id if pool_task else None,
        attempt_number=attempt_number,
        started_at=datetime.utcnow(),
        status="в работе",
    )
    db.add(attempt)
    if pool_task:
        pool_task.status = "в работе"
        pool_task.pool.status = "в работе"
    db.commit()
    db.refresh(attempt)
    return _attempt_to_read(attempt)


@app.post("/attempts/{attempt_id}/submit", response_model=schemas.AttemptCommitResponse)
@app.post("/attempts/{attempt_id}/commit", response_model=schemas.AttemptCommitResponse)
async def submit_attempt(
    attempt_id: int,
    file: UploadFile | None = File(default=None),
    solution_files: List[UploadFile] | None = File(default=None),
    student_text_answer: str | None = Form(default=None),
    student_comment: str | None = Form(default=None),
    client_duration_seconds: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    attempt = _get_attempt_or_404(db, attempt_id)
    if attempt.committed_at is not None:
        raise HTTPException(status_code=409, detail="Попытка уже отправлена. Создайте новую попытку для исправления.")
    text_answer = (student_text_answer or "").strip()
    comment = (student_comment or "").strip()

    uploads = _normalize_solution_uploads(file, solution_files)
    if attempt.task.part == 2 and not uploads:
        raise HTTPException(status_code=422, detail="Для второй части загрузите одну или несколько страниц решения: JPG, PNG или PDF.")
    if not uploads and not text_answer:
        raise HTTPException(status_code=422, detail="Введите краткий ответ или загрузите файл решения.")
    if len(uploads) > MAX_SOLUTION_PAGES:
        raise HTTPException(status_code=422, detail=f"Можно загрузить не более {MAX_SOLUTION_PAGES} файлов решения за одну попытку.")

    saved_files: list[tuple[str, str]] = []
    for upload in uploads:
        saved_path, saved_name = await _save_upload(upload)
        if saved_path and saved_name:
            saved_files.append((saved_path, saved_name))
    committed_at = datetime.utcnow()
    attempt.committed_at = committed_at
    server_duration = max(0, int((committed_at - attempt.started_at).total_seconds()))
    attempt.duration_seconds = max(0, int(client_duration_seconds)) if client_duration_seconds is not None else server_duration
    attempt.uploaded_file_path = saved_files[0][0] if saved_files else None
    attempt.uploaded_file_name = saved_files[0][1] if saved_files else None
    attempt.student_text_answer = text_answer or comment
    attempt.status = "отправлено"
    for index, (saved_path, saved_name) in enumerate(saved_files, start=1):
        db.add(
            models.AttemptSolutionPage(
                attempt_id=attempt.id,
                file_path=saved_path,
                page_order=index,
                original_filename=saved_name,
                uploaded_at=committed_at,
            )
        )
    if attempt.pool_task:
        attempt.pool_task.status = "отправлено"
    db.flush()
    review = review_agent.run_pipeline(db, attempt)
    try:
        forecast_service.forecast(db, attempt.user_id, attempt.task.course_id, save_snapshot=True)
    except Exception:
        pass
    db.commit()
    db.refresh(attempt)
    return {
        "attempt": _attempt_to_read(attempt),
        "pipeline": [_pipeline_to_read(step) for step in attempt.pipeline_steps],
        "review": _review_to_read(review),
        "duration_seconds": attempt.duration_seconds,
        "status": attempt.status,
    }


@app.get("/attempts/{attempt_id}", response_model=schemas.AttemptRead)
def get_attempt(attempt_id: int, db: Session = Depends(get_db)) -> dict:
    return _attempt_to_read(_get_attempt_or_404(db, attempt_id))


@app.get("/solutions/{attempt_id}/file")
def get_solution_file(
    attempt_id: int,
    viewer_id: int | None = Query(default=None),
    download: bool = Query(default=False),
    x_user_id: int | None = Header(default=None),
    db: Session = Depends(get_db),
):
    attempt = _get_attempt_or_404(db, attempt_id)
    viewer = _get_user_or_404(db, viewer_id or x_user_id) if (viewer_id or x_user_id) else None
    if viewer is None:
        raise HTTPException(status_code=401, detail="Для просмотра файла решения укажите пользователя.")
    if not _can_access_solution(db, viewer, attempt):
        raise HTTPException(status_code=403, detail="Нет доступа к файлу решения.")
    file_path = _safe_solution_file_path(attempt)
    filename = attempt.uploaded_file_name or file_path.name
    disposition = "attachment" if download else "inline"
    return FileResponse(path=file_path, filename=filename, media_type=None, content_disposition_type=disposition)


@app.get("/solution-pages/{page_id}/file")
def get_solution_page_file(
    page_id: int,
    viewer_id: int | None = Query(default=None),
    download: bool = Query(default=False),
    x_user_id: int | None = Header(default=None),
    db: Session = Depends(get_db),
):
    page = db.get(models.AttemptSolutionPage, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Страница решения не найдена.")
    attempt = page.attempt
    viewer = _get_user_or_404(db, viewer_id or x_user_id) if (viewer_id or x_user_id) else None
    if viewer is None:
        raise HTTPException(status_code=401, detail="Для просмотра страницы решения укажите пользователя.")
    if not _can_access_solution(db, viewer, attempt):
        raise HTTPException(status_code=403, detail="Нет доступа к странице решения.")
    file_path = _safe_uploaded_file_path(page.file_path)
    disposition = "attachment" if download else "inline"
    return FileResponse(path=file_path, filename=page.original_filename, media_type=None, content_disposition_type=disposition)


@app.get("/tasks/{task_id}/attempts", response_model=List[schemas.AttemptRead])
def get_task_attempts(task_id: int, user_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> list[dict]:
    _get_task_or_404(db, task_id)
    query = db.query(models.Attempt).filter(models.Attempt.task_id == task_id)
    if user_id:
        query = query.filter(models.Attempt.user_id == user_id)
    return [_attempt_to_read(attempt) for attempt in query.order_by(models.Attempt.id.desc()).all()]


@app.post("/attempts/{attempt_id}/check", response_model=schemas.AttemptCommitResponse)
def check_attempt(attempt_id: int, db: Session = Depends(get_db)) -> dict:
    attempt = _get_attempt_or_404(db, attempt_id)
    review = review_agent.run_pipeline(db, attempt)
    db.commit()
    db.refresh(attempt)
    return {
        "attempt": _attempt_to_read(attempt),
        "pipeline": [_pipeline_to_read(step) for step in attempt.pipeline_steps],
        "review": _review_to_read(review),
        "duration_seconds": attempt.duration_seconds,
        "status": attempt.status,
    }


@app.get("/attempts/{attempt_id}/pipeline", response_model=List[schemas.PipelineStepRead])
def get_attempt_pipeline(attempt_id: int, db: Session = Depends(get_db)) -> list[models.CheckPipelineStep]:
    attempt = _get_attempt_or_404(db, attempt_id)
    return attempt.pipeline_steps


@app.get("/attempts/{attempt_id}/review", response_model=List[schemas.AIReviewRead])
def get_attempt_review(attempt_id: int, db: Session = Depends(get_db)) -> list[models.AIReview]:
    attempt = _get_attempt_or_404(db, attempt_id)
    return attempt.ai_reviews


@app.post("/attempts/{attempt_id}/teacher-comments", response_model=schemas.TeacherCommentRead)
def add_teacher_comment(attempt_id: int, payload: schemas.TeacherCommentCreate, db: Session = Depends(get_db)) -> models.TeacherComment:
    _get_attempt_or_404(db, attempt_id)
    teacher = _get_user_or_404(db, payload.teacher_id)
    if teacher.role not in {"Teacher", "Admin"}:
        raise HTTPException(status_code=403, detail="Комментарий может оставить преподаватель или администратор")
    comment = models.TeacherComment(
        attempt_id=attempt_id,
        teacher_id=teacher.id,
        comment_text=payload.comment_text,
        final_score=payload.final_score,
        status=payload.status,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@app.post("/ai/chat", response_model=schemas.AIChatResponse)
def ai_chat(payload: schemas.AIChatRequest, db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, payload.user_id)
    return tutor_agent.answer(
        db,
        user_id=payload.user_id,
        message=payload.message,
        course_id=payload.course_id,
        topic_id=payload.topic_id,
        task_id=payload.task_id,
        attempt_id=payload.attempt_id,
    )


@app.post("/ai/topic-guard", response_model=schemas.TopicGuardResponse)
def ai_topic_guard(payload: schemas.TopicGuardRequest) -> dict:
    return topic_guard.classify(payload.message)


@app.post("/tasks/{task_id}/generate-similar", response_model=schemas.SimilarTasksResponse)
def generate_similar_tasks(task_id: int, count: int = Query(default=5, ge=1, le=8), db: Session = Depends(get_db)) -> dict:
    task = _get_task_or_404(db, task_id)
    return {"source_task_id": task.id, "tasks": task_generator.generate_similar(task, count=count)}


@app.get("/users/{user_id}/analytics", response_model=schemas.AnalyticsRead)
def get_user_analytics(user_id: int, course_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, user_id)
    return forecast_service.analytics(db, user_id, course_id)


@app.get("/users/{user_id}/forecast", response_model=schemas.ForecastRead)
def get_user_forecast(user_id: int, course_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, user_id)
    forecast = forecast_service.forecast(db, user_id, course_id)
    forecast.pop("risks", None)
    db.commit()
    return forecast


@app.get("/users/{user_id}/recommendations")
def get_user_recommendations(
    user_id: int,
    course_id: int | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
) -> list[dict]:
    _get_user_or_404(db, user_id)
    return recommend_next_tasks(db, user_id, course_id=course_id, limit=limit)


@app.get("/users/{user_id}/parent-report", response_model=schemas.ParentReportRead)
def get_parent_report(user_id: int, db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, user_id)
    return forecast_service.parent_report(db, user_id)


@app.get("/teacher/dashboard", response_model=schemas.TeacherDashboardRead)
def get_teacher_dashboard(db: Session = Depends(get_db)) -> dict:
    dashboard = forecast_service.teacher_dashboard(db)
    attempts = db.query(models.Attempt).filter(models.Attempt.committed_at.isnot(None)).all()
    students_count = db.query(models.User).filter(models.User.role == "Student").count()
    checked_by_ai = sum(1 for attempt in attempts if attempt.ai_reviews)
    manual_required = sum(1 for attempt in attempts if attempt.status in {"отправлено", "требует ручной проверки", "нужна ручная проверка", "manual_review"})
    correct_values = [1 if attempt.is_correct else 0 for attempt in attempts if attempt.is_correct is not None]
    dashboard["summary"] = {
        "students_total": students_count,
        "works_for_review": sum(1 for attempt in attempts if attempt.status in {"отправлено", "проверено", "проверено ИИ", "требует ручной проверки", "нужна ручная проверка", "manual_review"}),
        "checked_by_ai": checked_by_ai,
        "manual_required": manual_required,
        "average_correct_percent": round(sum(correct_values) / len(correct_values) * 100, 1) if correct_values else 0,
    }
    return dashboard


@app.get("/teacher/attempts")
def get_teacher_attempts(
    request: Request,
    user_id: int | None = Query(default=None),
    course_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    topic_id: int | None = Query(default=None),
    section_id: int | None = Query(default=None),
    task_title: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    if _wants_html(request):
        user = _resolve_session_user_or_login(request, db, user_id)
        if not isinstance(user, models.User):
            return user
        if _role_key(user) not in {"teacher", "admin"}:
            return _forbidden_page(request, "Список работ доступен только преподавателю.")
        return templates.TemplateResponse(
            request=request,
            name="teacher_attempts.html",
            context={"current_user": user, "active_page": "teacher_attempts"},
        )

    query = db.query(models.Attempt).join(models.Task)
    if user_id:
        query = query.filter(models.Attempt.user_id == user_id)
    if course_id:
        query = query.filter(models.Task.course_id == course_id)
    if status_filter:
        if status_filter == "проверено ИИ":
            query = query.filter(models.Attempt.status.in_(["проверено", "проверено ИИ"]))
        elif status_filter in {"требует ручной проверки", "нужна ручная проверка", "manual_review"}:
            query = query.filter(models.Attempt.status.in_(["требует ручной проверки", "нужна ручная проверка", "manual_review"]))
        else:
            query = query.filter(models.Attempt.status == status_filter)
    if topic_id:
        query = query.filter(models.Task.topic_id == topic_id)
    if section_id:
        query = query.filter(models.Task.section_id == section_id)
    if task_title:
        query = query.filter(models.Task.title.ilike(f"%{task_title}%"))
    if date_from:
        query = query.filter(models.Attempt.committed_at >= date_from)
    if date_to:
        query = query.filter(models.Attempt.committed_at <= date_to)
    return [
        _teacher_attempt_summary(attempt)
        for attempt in query.order_by(models.Attempt.committed_at.desc(), models.Attempt.id.desc()).limit(250).all()
    ]


@app.get("/teacher/attempts/{attempt_id}")
def get_teacher_attempt_detail(
    attempt_id: int,
    request: Request,
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    attempt = _get_attempt_or_404(db, attempt_id)
    if _wants_html(request):
        user = _resolve_session_user_or_login(request, db, user_id)
        if not isinstance(user, models.User):
            return user
        if _role_key(user) not in {"teacher", "admin"}:
            return _forbidden_page(request, "Карточка работы доступна только преподавателю.")
        return templates.TemplateResponse(
            request=request,
            name="teacher_attempt_detail.html",
            context={
                "current_user": user,
                "attempt": attempt,
                "attempt_id": attempt.id,
                "active_page": "teacher_attempts",
            },
        )
    return _teacher_attempt_detail(db, attempt)


@app.post("/teacher/attempts/{attempt_id}/comment", response_model=schemas.TeacherCommentRead)
def save_teacher_attempt_comment(
    attempt_id: int,
    payload: schemas.TeacherCommentCreate,
    db: Session = Depends(get_db),
) -> dict:
    attempt = _get_attempt_or_404(db, attempt_id)
    teacher = _get_user_or_404(db, payload.teacher_id)
    if teacher.role not in {"Teacher", "Admin"}:
        raise HTTPException(status_code=403, detail="Комментарий может оставить преподаватель или администратор")
    comment = models.TeacherComment(
        attempt_id=attempt.id,
        teacher_id=teacher.id,
        comment_text=payload.comment_text,
        final_score=payload.final_score,
        status=payload.status,
    )
    attempt.status = payload.status
    if payload.final_score is not None:
        attempt.score = payload.final_score
    if payload.status == "зачтено":
        attempt.is_correct = True
    elif payload.status in {"не зачтено", "требуется исправление", "требует ручной проверки", "нужна ручная проверка"}:
        attempt.is_correct = False
    if attempt.pool_task:
        attempt.pool_task.status = payload.status
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _teacher_comment_to_read(comment)


@app.post("/teacher/attempts/{attempt_id}/status")
def update_teacher_attempt_status(
    attempt_id: int,
    payload: schemas.TeacherAttemptStatusUpdate,
    db: Session = Depends(get_db),
) -> dict:
    attempt = _get_attempt_or_404(db, attempt_id)
    allowed_statuses = {
        "не начато",
        "в работе",
        "отправлено",
        "проверено ИИ",
        "проверено преподавателем",
        "требуется исправление",
        "требует ручной проверки",
        "нужна ручная проверка",
        "manual_review",
        "зачтено",
        "не зачтено",
    }
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Недопустимый статус проверки")
    attempt.status = payload.status
    if payload.score is not None:
        attempt.score = payload.score
    if payload.status == "зачтено":
        attempt.is_correct = True
    elif payload.status in {"не зачтено", "требуется исправление"}:
        attempt.is_correct = False
    if attempt.pool_task:
        attempt.pool_task.status = payload.status
    db.commit()
    db.refresh(attempt)
    return _teacher_attempt_detail(db, attempt)


@app.post("/teacher/tasks/{task_id}/reference-solution")
def update_task_reference_solution_legacy(
    task_id: int,
    payload: schemas.TaskReferenceSolutionUpdate,
    db: Session = Depends(get_db),
) -> dict:
    teacher = _get_user_or_404(db, payload.teacher_id)
    if _role_key(teacher) != "admin":
        raise HTTPException(status_code=403, detail="Ответ и эталонное решение может изменить только администратор")
    task = _get_task_or_404(db, task_id)
    task.solution = payload.reference_solution.strip()
    task.solution_explanation = payload.reference_solution.strip()
    if payload.correct_answer is not None and payload.correct_answer.strip():
        task.correct_answer = payload.correct_answer.strip()
        task.answer = payload.correct_answer.strip()
    if payload.criteria is not None and payload.criteria.strip():
        task.criteria = payload.criteria.strip()
    db.commit()
    db.refresh(task)
    return {
        "task_id": task.id,
        "reference_solution": task.solution,
        "solution_explanation": task.solution_explanation,
        "correct_answer": task.correct_answer,
        "criteria": task.criteria,
        "message": "Эталонное решение сохранено. Оно будет использоваться при следующих ИИ-проверках этой задачи.",
    }


@app.post("/admin/tasks/{task_id}/reference-solution")
async def update_task_reference_solution_file(
    task_id: int,
    admin_id: int = Form(...),
    reference_file: UploadFile | None = File(default=None),
    reference_files: List[UploadFile] | None = File(default=None),
    correct_answer: str | None = Form(default=None),
    criteria: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    admin = _get_user_or_404(db, admin_id)
    if _role_key(admin) != "admin":
        raise HTTPException(status_code=403, detail="Ответ и эталонное решение может изменить только администратор")
    task = _get_task_or_404(db, task_id)
    uploads = _normalize_solution_uploads(reference_file, reference_files)
    if len(uploads) > MAX_SOLUTION_PAGES:
        raise HTTPException(status_code=422, detail=f"Можно загрузить не более {MAX_SOLUTION_PAGES} файлов эталонного решения.")
    old_paths = []
    if uploads:
        if task.reference_solution_file_path:
            old_paths.append(task.reference_solution_file_path)
        old_paths.extend(page.file_path for page in task.reference_solution_pages if page.file_path)
        for page in list(task.reference_solution_pages):
            db.delete(page)
        db.flush()

        saved_files: list[tuple[str, str]] = []
        for upload in uploads:
            saved_path, saved_name = await _save_upload(upload)
            saved_files.append((saved_path, saved_name))

        for index, (saved_path, saved_name) in enumerate(saved_files, start=1):
            db.add(
                models.TaskReferenceSolutionPage(
                    task_id=task.id,
                    file_path=saved_path,
                    page_order=index,
                    original_filename=saved_name,
                )
            )
        task.reference_solution_file_path = saved_files[0][0]
        task.reference_solution_file_name = saved_files[0][1]
        task.solution = f"Эталонное решение загружено страницами: {len(saved_files)}"
        task.solution_explanation = task.solution
    if correct_answer is not None and correct_answer.strip():
        task.correct_answer = correct_answer.strip()
        task.answer = correct_answer.strip()
    if criteria is not None and criteria.strip():
        task.criteria = criteria.strip()
    db.commit()
    db.refresh(task)
    for file_path in set(old_paths):
        if not _uploaded_file_is_referenced(db, file_path):
            _delete_uploaded_file_if_unused(file_path)
    return {
        "task_id": task.id,
        "reference_solution_file_path": task.reference_solution_file_path,
        "reference_solution_file_name": task.reference_solution_file_name,
        "reference_solution_file_url": _task_reference_file_url(task, admin.id) if task.reference_solution_file_path else None,
        "reference_solution_pages": _task_reference_pages_info(task, admin.id),
        "correct_answer": task.correct_answer,
        "criteria": task.criteria,
        "message": "Эталонное решение сохранено файлом. Оно будет использоваться при следующих проверках этой задачи.",
    }


@app.get("/admin/tasks/{task_id}/reference-solution/file")
def get_task_reference_solution_file(
    task_id: int,
    viewer_id: int | None = Query(default=None),
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    viewer = _get_user_or_404(db, viewer_id) if viewer_id else None
    if viewer is None or _role_key(viewer) != "admin":
        raise HTTPException(status_code=403, detail="Файл эталонного решения доступен только администратору")
    task = _get_task_or_404(db, task_id)
    first_page = task.reference_solution_pages[0] if task.reference_solution_pages else None
    file_path_value = task.reference_solution_file_path or (first_page.file_path if first_page else None)
    file_name = task.reference_solution_file_name or (first_page.original_filename if first_page else None)
    if not file_path_value:
        raise HTTPException(status_code=404, detail="Файл эталонного решения не загружен")
    file_path = _safe_uploaded_file_path(file_path_value)
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        filename=file_name or file_path.name,
        media_type=None,
        content_disposition_type=disposition,
    )


@app.get("/admin/task-reference-pages/{page_id}/file")
def get_task_reference_solution_page_file(
    page_id: int,
    viewer_id: int | None = Query(default=None),
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    viewer = _get_user_or_404(db, viewer_id) if viewer_id else None
    if viewer is None or _role_key(viewer) != "admin":
        raise HTTPException(status_code=403, detail="Страницы эталонного решения доступны только администратору")
    page = db.get(models.TaskReferenceSolutionPage, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Страница эталонного решения не найдена")
    file_path = _safe_uploaded_file_path(page.file_path)
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=file_path,
        filename=page.original_filename or file_path.name,
        media_type=None,
        content_disposition_type=disposition,
    )


@app.post("/admin/tasks", status_code=status.HTTP_201_CREATED)
def create_admin_task(payload: schemas.TaskAdminCreate, db: Session = Depends(get_db)) -> dict:
    admin = _get_user_or_404(db, payload.admin_id)
    if _role_key(admin) != "admin":
        raise HTTPException(status_code=403, detail="Задание может добавить только администратор")
    course = _get_course_or_404(db, payload.course_id)
    section = _get_section_or_404(db, payload.section_id)
    topic = _get_topic_or_404(db, payload.topic_id)
    task = models.Task(
        course_id=course.id,
        section_id=section.id,
        topic_id=topic.id,
        title=payload.title,
        condition_text=payload.condition_text,
        correct_answer=payload.correct_answer,
        answer=payload.correct_answer,
        solution_explanation="Эталонное решение добавляется администратором отдельным файлом.",
        solution="",
        criteria=payload.criteria,
        part=payload.part,
        task_number=payload.task_number,
        exam_type=course.exam_type,
        task_type="экзаменационное задание",
        answer_format="развёрнутое решение" if payload.part == 2 else "краткий ответ",
        difficulty=payload.difficulty,
        max_score=payload.max_score,
        is_active=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_read(task, db=db)


@app.delete("/admin/tasks/{task_id}")
def delete_admin_task(task_id: int, admin_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    admin = _get_user_or_404(db, admin_id)
    if _role_key(admin) != "admin":
        raise HTTPException(status_code=403, detail="Задание может удалить только администратор")
    task = _get_task_or_404(db, task_id)
    task.is_active = False
    db.commit()
    return {"task_id": task.id, "is_active": False, "message": "Задание отключено из банка заданий."}


@app.delete("/admin/attempts/{attempt_id}")
def delete_admin_attempt(attempt_id: int, admin_id: int = Query(...), db: Session = Depends(get_db)) -> dict:
    admin = _get_user_or_404(db, admin_id)
    if _role_key(admin) != "admin":
        raise HTTPException(status_code=403, detail="Ответы учеников может удалять только администратор")
    attempt = _get_attempt_or_404(db, attempt_id)
    task_id = attempt.task_id
    user_id = attempt.user_id
    pool_task = attempt.pool_task
    file_paths = []
    if attempt.uploaded_file_path:
        file_paths.append(attempt.uploaded_file_path)
    file_paths.extend(page.file_path for page in attempt.solution_pages if page.file_path)

    db.delete(attempt)
    db.flush()

    if pool_task:
        latest_attempt = (
            db.query(models.Attempt)
            .filter(models.Attempt.pool_task_id == pool_task.id)
            .order_by(models.Attempt.id.desc())
            .first()
        )
        pool_task.status = latest_attempt.status if latest_attempt else "не начато"
    files_to_delete = [file_path for file_path in set(file_paths) if not _uploaded_file_is_referenced(db, file_path)]
    db.commit()

    for file_path in files_to_delete:
        _delete_uploaded_file_if_unused(file_path)

    return {
        "attempt_id": attempt_id,
        "task_id": task_id,
        "user_id": user_id,
        "message": "Ответ ученика и связанные данные проверки удалены администратором.",
    }


@app.post("/purchase-requests", response_model=schemas.PurchaseRequestRead, status_code=status.HTTP_201_CREATED)
def create_purchase_request(payload: schemas.PurchaseRequestCreate, db: Session = Depends(get_db)) -> dict:
    _get_user_or_404(db, payload.user_id)
    _get_course_or_404(db, payload.course_id)
    request = models.PurchaseRequest(
        user_id=payload.user_id,
        course_id=payload.course_id,
        tariff_type=payload.tariff_type,
        status="создана",
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    data = schemas.PurchaseRequestRead.model_validate(request).model_dump()
    data["message"] = "Учебный режим: заявка на курс успешно создана"
    return data


@app.post("/train", response_model=schemas.TrainResponse)
def train_forecast_model(db: Session = Depends(get_db)) -> dict:
    return forecast_service.train_quality_model(db)


def _normalize_solution_uploads(
    legacy_file: UploadFile | None,
    solution_files: list[UploadFile] | None,
) -> list[UploadFile]:
    uploads: list[UploadFile] = []
    if solution_files:
        uploads.extend(upload for upload in solution_files if upload and upload.filename)
    if legacy_file is not None and legacy_file.filename:
        uploads.append(legacy_file)
    return uploads


async def _save_upload(file: UploadFile | None) -> tuple[str | None, str | None]:
    if file is None or not file.filename:
        return None, None
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Можно загрузить только JPG, JPEG, PNG или PDF.")
    safe_name = f"{uuid4().hex}{suffix}"
    target = UPLOAD_DIR / safe_name
    content = await file.read()
    if len(content) > MAX_UPLOAD_FILE_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Файл «{file.filename}» слишком большой. Максимальный размер одного файла — {MAX_UPLOAD_FILE_SIZE // (1024 * 1024)} МБ.",
        )
    target.write_bytes(content)
    return str(target).replace("\\", "/"), file.filename


def _get_user_or_404(db: Session, user_id: int) -> models.User:
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def _resolve_session_user(db: Session, user_id: int | None, preferred_roles: set[str] | None = None) -> models.User:
    if user_id:
        return _get_user_or_404(db, user_id)
    query = db.query(models.User)
    if preferred_roles:
        user = query.filter(models.User.role.in_(preferred_roles)).order_by(models.User.id.asc()).first()
        if user:
            return user
    user = query.order_by(models.User.id.asc()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователи не найдены")
    return user


def _resolve_session_user_or_login(request: Request, db: Session, user_id: int | None):
    if user_id is None:
        return _login_required_page(request)
    return _get_user_or_404(db, user_id)


def _login_required_page(request: Request):
    return _message_response(
        request,
        title="Нужен вход",
        message="Выберите тестового пользователя на главной странице и нажмите «Войти». После этого меню откроет разделы по роли.",
        label="Доступ",
        active_page="login",
        primary_href=str(request.url_for("login_page")),
        primary_text="Перейти ко входу",
        status_code=401,
    )


def _forbidden_page(request: Request, message: str):
    return _message_response(
        request,
        title="Раздел недоступен",
        message=message,
        label="Ограничение доступа",
        active_page="home",
        primary_href=str(request.url_for("index")),
        primary_text="На главную",
        status_code=403,
    )


def _message_response(
    request: Request,
    title: str,
    message: str,
    label: str = "Информация",
    active_page: str = "home",
    primary_href: str | None = None,
    primary_text: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="message.html",
        context={
            "title": title,
            "message": message,
            "label": label,
            "active_page": active_page,
            "primary_href": primary_href,
            "primary_text": primary_text,
        },
        status_code=status_code,
    )


def _get_course_or_404(db: Session, course_id: int) -> models.Course:
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")
    return course


def _get_section_or_404(db: Session, section_id: int) -> models.ExamSection:
    section = db.get(models.ExamSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Раздел не найден")
    return section


def _get_topic_or_404(db: Session, topic_id: int) -> models.Topic:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Тема не найдена")
    return topic


def _get_task_or_404(db: Session, task_id: int) -> models.Task:
    task = db.get(models.Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return task


def _get_pool_or_404(db: Session, pool_id: int) -> models.AssignmentPool:
    pool = db.get(models.AssignmentPool, pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="Пул заданий не найден")
    return pool


def _get_attempt_or_404(db: Session, attempt_id: int) -> models.Attempt:
    attempt = db.get(models.Attempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Попытка не найдена")
    return attempt


def _role_key(user: models.User) -> str:
    role = (user.role or "").strip().lower()
    aliases = {
        "student": "student",
        "ученик": "student",
        "teacher": "teacher",
        "преподаватель": "teacher",
        "parent": "parent",
        "родитель": "parent",
        "admin": "admin",
        "администратор": "admin",
    }
    return aliases.get(role, role)


def _can_access_solution(db: Session, viewer: models.User, attempt: models.Attempt) -> bool:
    role = _role_key(viewer)
    if role == "admin":
        return True
    if role == "student":
        return viewer.id == attempt.user_id
    if role == "teacher":
        return True
    if role == "parent":
        child = _child_for_parent(db, viewer)
        return bool(child and child.id == attempt.user_id)
    return False


def _safe_solution_file_path(attempt: models.Attempt) -> Path:
    file_path = attempt.uploaded_file_path
    if not file_path and attempt.solution_pages:
        file_path = attempt.solution_pages[0].file_path
    if not file_path:
        raise HTTPException(status_code=404, detail="Файл решения отсутствует.")
    return _safe_uploaded_file_path(file_path)


def _safe_uploaded_file_path(file_path: str) -> Path:
    raw_path = Path(file_path)
    full_path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
    resolved = full_path.resolve()
    uploads_root = (Path.cwd() / UPLOAD_DIR).resolve()
    if resolved != uploads_root and uploads_root not in resolved.parents:
        raise HTTPException(status_code=403, detail="Недопустимый путь к файлу решения.")
    if resolved.suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Недопустимый формат файла решения.")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Файл решения не найден на диске.")
    return resolved


def _uploaded_file_is_referenced(db: Session, file_path: str) -> bool:
    return bool(
        db.query(models.Attempt).filter(models.Attempt.uploaded_file_path == file_path).first()
        or db.query(models.AttemptSolutionPage).filter(models.AttemptSolutionPage.file_path == file_path).first()
        or db.query(models.Task).filter(models.Task.reference_solution_file_path == file_path).first()
        or db.query(models.TaskReferenceSolutionPage).filter(models.TaskReferenceSolutionPage.file_path == file_path).first()
    )


def _delete_uploaded_file_if_unused(file_path: str) -> None:
    try:
        resolved = _safe_uploaded_file_path(file_path)
    except HTTPException:
        return
    try:
        resolved.unlink(missing_ok=True)
    except OSError:
        return


def _default_reviewer_id(db: Session) -> int | None:
    reviewer = (
        db.query(models.User)
        .filter(models.User.role.in_(["Teacher", "Admin", "teacher", "admin", "преподаватель", "администратор"]))
        .order_by(models.User.role.desc(), models.User.id.asc())
        .first()
    )
    return reviewer.id if reviewer else None


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def _course_for_user(db: Session, user: models.User) -> models.Course:
    return db.query(models.Course).filter(models.Course.exam_type == user.target_exam).first() or db.query(models.Course).first()


def _child_for_parent(db: Session, user: models.User) -> models.User | None:
    if _role_key(user) == "admin":
        return _first_student(db)
    preferred = (
        db.query(models.User)
        .filter(models.User.email == "boris@example.com")
        .filter(models.User.role.in_(["Student", "student", "ученик"]))
        .first()
    )
    if preferred:
        return preferred
    return (
        db.query(models.User)
        .filter(models.User.role.in_(["Student", "student", "ученик"]))
        .filter(models.User.target_exam == user.target_exam)
        .filter(models.User.email != "student@example.com")
        .order_by(models.User.id.asc())
        .first()
        or _first_student(db)
    )


def _first_student(db: Session) -> models.User | None:
    return (
        db.query(models.User)
        .filter(models.User.role.in_(["Student", "student", "ученик"]))
        .order_by(models.User.id.asc())
        .first()
    )


def _admin_stats(db: Session) -> dict:
    attempts = db.query(models.Attempt).filter(models.Attempt.committed_at.isnot(None)).all()
    checked = [attempt for attempt in attempts if attempt.status in {"проверено", "проверено ИИ", "проверено преподавателем", "зачтено"}]
    return {
        "users": db.query(models.User).count(),
        "students": db.query(models.User).filter(models.User.role.in_(["Student", "student", "ученик"])).count(),
        "teachers": db.query(models.User).filter(models.User.role.in_(["Teacher", "teacher", "преподаватель"])).count(),
        "parents": db.query(models.User).filter(models.User.role.in_(["Parent", "parent", "родитель"])).count(),
        "courses": db.query(models.Course).count(),
        "tasks": db.query(models.Task).count(),
        "attempts": len(attempts),
        "checked_attempts": len(checked),
    }


def _format_seconds(value: int | float | None) -> str:
    seconds = int(value or 0)
    if seconds <= 0:
        return "0 сек"
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {minutes:02d} мин {rest:02d} сек"
    if minutes:
        return f"{minutes} мин {rest:02d} сек"
    return f"{rest} сек"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")


def _user_pools(db: Session, user_id: int) -> list[models.AssignmentPool]:
    return db.query(models.AssignmentPool).filter(models.AssignmentPool.user_id == user_id).order_by(models.AssignmentPool.deadline.asc()).all()


def _user_attempts(db: Session, user_id: int, limit: int = 20) -> list[models.Attempt]:
    return db.query(models.Attempt).filter(models.Attempt.user_id == user_id).order_by(models.Attempt.id.desc()).limit(limit).all()


def _course_detail_to_read(db: Session, course: models.Course, user_id: int | None = None) -> dict:
    data = _course_to_read(db, course, user_id)
    data["sections"] = [_section_to_read(section, db=db, user_id=user_id) for section in course.sections]
    data["topics"] = [_topic_to_read(topic, db=db, user_id=user_id) for topic in course.topics[:12]]
    data["first_tasks"] = [
        _task_to_read(task, db=db, user_id=user_id)
        for task in db.query(models.Task).filter(models.Task.course_id == course.id).order_by(models.Task.id).limit(8)
    ]
    return data


def _section_detail_to_read(db: Session, section: models.ExamSection, user_id: int | None = None) -> dict:
    data = _section_to_read(section, db=db, user_id=user_id)
    data["course"] = _course_to_read(db, section.course, user_id)
    data["topics"] = [
        {
            **_topic_to_read(topic, db=db, user_id=user_id),
            "tasks": [_task_to_read(task, db=db, user_id=user_id) for task in topic.tasks],
        }
        for topic in section.topics
    ]
    data["tasks"] = [_task_to_read(task, db=db, user_id=user_id) for task in section.tasks]
    data["theory"] = (
        f"{section.title} — модуль экзамена {section.course.exam_type}. "
        "Изучите теорию по темам, затем решайте задания по таймеру и сохраняйте каждую попытку."
    )
    return data


def _course_to_read(db: Session, course: models.Course, user_id: int | None = None) -> dict:
    readiness = 0.0
    predicted = 0.0
    completed_tasks = 0
    average_time = 0.0
    correct_percent = 0.0
    if user_id:
        try:
            forecast = forecast_service.forecast(db, user_id, course.id, save_snapshot=False)
            analytics = forecast_service.analytics(db, user_id, course.id)
            readiness = analytics["completion_percent"]
            predicted = forecast["expected_primary_score"]
            completed_tasks = len(
                {
                    attempt.task_id
                    for attempt in _course_attempts(db, user_id, course.id)
                    if attempt.status in {"проверено", "проверено ИИ", "проверено преподавателем", "зачтено"}
                }
            )
            average_time = analytics["average_time_seconds"]
            correct_percent = analytics["correct_percent"]
        except Exception:
            readiness = 0.0
            predicted = 0.0
    return {
        "id": course.id,
        "title": course.title,
        "exam_type": course.exam_type,
        "description": course.description,
        "format_with_teacher_price": course.format_with_teacher_price,
        "format_ai_price": course.format_ai_price,
        "section_count": len(course.sections),
        "topic_count": len(course.topics),
        "task_count": len(course.tasks),
        "completed_tasks": completed_tasks,
        "average_time_seconds": average_time,
        "correct_percent": correct_percent,
        "predicted_score": predicted,
        "readiness_percent": readiness,
        "created_at": course.created_at,
    }


def _section_to_read(section: models.ExamSection, db: Session | None = None, user_id: int | None = None) -> dict:
    completion_percent, average_result = _progress_for_tasks(db, user_id, [task.id for task in section.tasks])
    return {
        "id": section.id,
        "course_id": section.course_id,
        "number": section.number,
        "title": section.title,
        "description": section.description,
        "max_score": section.max_score,
        "topic_count": len(section.topics),
        "task_count": len(section.tasks),
        "completion_percent": completion_percent,
        "average_result_percent": average_result,
    }


def _topic_to_read(topic: models.Topic, db: Session | None = None, user_id: int | None = None) -> dict:
    mastery_percent, _ = _progress_for_tasks(db, user_id, [task.id for task in topic.tasks])
    return {
        "id": topic.id,
        "section_id": topic.section_id,
        "course_id": topic.course_id,
        "title": topic.title,
        "theory_content": topic.theory_content,
        "examples": topic.examples,
        "difficulty": topic.difficulty,
        "task_count": len(topic.tasks),
        "mastery_percent": mastery_percent,
        "material": _topic_material_to_read(_primary_topic_material(topic)),
    }


def _task_to_read(task: models.Task, db: Session | None = None, user_id: int | None = None) -> dict:
    attempts = []
    if db is not None and user_id is not None:
        attempts = (
            db.query(models.Attempt)
            .filter(models.Attempt.user_id == user_id)
            .filter(models.Attempt.task_id == task.id)
            .order_by(models.Attempt.id.desc())
            .all()
        )
    latest = attempts[0] if attempts else None
    average_time = (
        sum((attempt.duration_seconds or 0) for attempt in attempts if attempt.duration_seconds)
        / len([attempt for attempt in attempts if attempt.duration_seconds])
        if any(attempt.duration_seconds for attempt in attempts)
        else 0
    )
    return {
        "id": task.id,
        "topic_id": task.topic_id,
        "section_id": task.section_id,
        "course_id": task.course_id,
        "title": task.title,
        "condition_text": task.condition_text,
        "correct_answer": task.correct_answer,
        "solution_explanation": task.solution_explanation,
        "material": _topic_material_to_read(_primary_topic_material(task.topic)) if task.topic else None,
        "exam_type": task.exam_type,
        "part": task.part,
        "task_number": task.task_number,
        "prototype_number": task.prototype_number,
        "analog_number": task.analog_number,
        "bank_topic": task.bank_topic,
        "image_path": task.image_path,
        "image_url": _static_asset_url(task.image_path),
        "context_image_path": task.context_image_path,
        "context_image_url": _static_asset_url(task.context_image_path),
        "answer": task.answer,
        "solution": task.solution,
        "reference_solution_file_path": task.reference_solution_file_path,
        "reference_solution_file_name": task.reference_solution_file_name,
        "reference_solution_file_url": _task_reference_file_url(task, user_id) if task.reference_solution_file_path and user_id else None,
        "reference_solution_pages": _task_reference_pages_info(task, user_id),
        "source_file": task.source_file,
        "source_page": task.source_page,
        "is_active": task.is_active,
        "task_type": task.task_type,
        "answer_format": task.answer_format,
        "criteria": task.criteria,
        "difficulty": task.difficulty,
        "max_score": task.max_score,
        "section_number": task.section.number if task.section else None,
        "section_title": task.section.title if task.section else None,
        "topic_title": task.topic.title if task.topic else None,
        "course_title": task.course.title if task.course else None,
        "status": latest.status if latest else "не начато",
        "average_time_seconds": round(average_time, 1),
        "attempts_count": len(attempts),
    }


def _primary_topic_material(topic: models.Topic | None) -> models.TopicMaterial | None:
    if not topic or not topic.materials:
        return None
    return topic.materials[0]


def _topic_material_to_read(material: models.TopicMaterial | None) -> dict | None:
    if not material:
        return None
    return {
        "id": material.id,
        "topic_id": material.topic_id,
        "title": material.title,
        "content": material.content,
        "examples": material.examples,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }


def _course_attempts(db: Session, user_id: int, course_id: int) -> list[models.Attempt]:
    return (
        db.query(models.Attempt)
        .join(models.Task)
        .filter(models.Attempt.user_id == user_id)
        .filter(models.Task.course_id == course_id)
        .all()
    )


def _progress_for_tasks(db: Session | None, user_id: int | None, task_ids: list[int]) -> tuple[float, float]:
    if db is None or user_id is None or not task_ids:
        return 0.0, 0.0
    attempts = (
        db.query(models.Attempt)
        .filter(models.Attempt.user_id == user_id)
        .filter(models.Attempt.task_id.in_(task_ids))
        .all()
    )
    if not attempts:
        return 0.0, 0.0
    completed_task_ids = {
        attempt.task_id
        for attempt in attempts
        if attempt.status in {"проверено", "проверено ИИ", "проверено преподавателем", "зачтено"}
    }
    best_scores: dict[int, float] = {}
    max_scores: dict[int, float] = {}
    for attempt in attempts:
        max_scores[attempt.task_id] = attempt.task.max_score or 1
        best_scores[attempt.task_id] = max(best_scores.get(attempt.task_id, 0), attempt.score or 0)
    completion = len(completed_task_ids) / len(task_ids) * 100
    average_result = (
        sum((best_scores.get(task_id, 0) / max_scores.get(task_id, 1)) for task_id in task_ids)
        / len(task_ids)
        * 100
    )
    return round(completion, 1), round(average_result, 1)


def _pool_to_read(pool: models.AssignmentPool, db: Session | None = None) -> dict:
    return {
        "id": pool.id,
        "user_id": pool.user_id,
        "course_id": pool.course_id,
        "title": pool.title,
        "period_start": pool.period_start,
        "period_end": pool.period_end,
        "deadline": pool.deadline,
        "status": pool.status,
        "completion_percent": pool.completion_percent,
        "course_title": pool.course.title if pool.course else None,
        "pool_tasks": [
            _pool_task_to_read(item, db=db)
            for item in pool.pool_tasks
        ],
    }


def _pool_task_to_read(item: models.PoolTask, db: Session | None = None) -> dict:
    attempts = []
    if db is not None:
        attempts = (
            db.query(models.Attempt)
            .filter(models.Attempt.pool_task_id == item.id)
            .order_by(models.Attempt.id.desc())
            .all()
        )
    latest = attempts[0] if attempts else None
    average_time = (
        sum((attempt.duration_seconds or 0) for attempt in attempts if attempt.duration_seconds)
        / len([attempt for attempt in attempts if attempt.duration_seconds])
        if any(attempt.duration_seconds for attempt in attempts)
        else 0
    )
    result = "-"
    if latest and latest.is_correct is not None:
        result = "верно" if latest.is_correct else "ошибка"
    return {
        "id": item.id,
        "pool_id": item.pool_id,
        "task_id": item.task_id,
        "status": item.status,
        "deadline": item.pool.deadline,
        "module": item.task.section.title,
        "topic": item.task.topic.title,
        "attempts_count": len(attempts),
        "average_time_seconds": round(average_time, 1),
        "result": result,
        "task": _task_to_read(item.task, db=db, user_id=item.pool.user_id if item.pool else None),
    }


def _attempt_to_read(attempt: models.Attempt) -> dict:
    solution_pages = _attempt_solution_pages_info(attempt, attempt.user_id)
    file_url = _solution_file_url(attempt, attempt.user_id) if (attempt.uploaded_file_path or solution_pages) else None
    return {
        "id": attempt.id,
        "attempt_id": attempt.id,
        "user_id": attempt.user_id,
        "task_id": attempt.task_id,
        "pool_task_id": attempt.pool_task_id,
        "attempt_number": attempt.attempt_number,
        "started_at": attempt.started_at,
        "committed_at": attempt.committed_at,
        "duration_seconds": attempt.duration_seconds,
        "uploaded_file_path": attempt.uploaded_file_path,
        "uploaded_file_name": attempt.uploaded_file_name,
        "student_text_answer": attempt.student_text_answer,
        "recognized_text": attempt.recognized_text,
        "extracted_answer": attempt.extracted_answer,
        "is_correct": attempt.is_correct,
        "score": attempt.score,
        "status": attempt.status,
        "created_at": attempt.created_at,
        "task_title": attempt.task.title if attempt.task else None,
        "task_part": attempt.task.part if attempt.task else None,
        "course_id": attempt.task.course_id if attempt.task else None,
        "course_title": attempt.task.course.title if attempt.task and attempt.task.course else None,
        "section_title": attempt.task.section.title if attempt.task and attempt.task.section else None,
        "topic_title": attempt.task.topic.title if attempt.task and attempt.task.topic else None,
        "file_url": file_url,
        "solution_pages": solution_pages,
        "solution_pages_count": len(solution_pages),
        "task_condition": attempt.task.condition_text if attempt.task else None,
        "correct_answer": attempt.task.correct_answer if attempt.task and attempt.task.part == 1 else None,
        "criteria": attempt.task.criteria if attempt.task else None,
    }


def _teacher_attempt_summary(attempt: models.Attempt) -> dict:
    latest_review = attempt.ai_reviews[-1] if attempt.ai_reviews else None
    latest_comment = attempt.teacher_comments[-1] if attempt.teacher_comments else None
    task = attempt.task
    display_status = "проверено ИИ" if attempt.status == "проверено" else attempt.status
    return {
        **_attempt_to_read(attempt),
        "status": display_status,
        "student_name": attempt.user.name if attempt.user else "-",
        "student_grade": attempt.user.grade if attempt.user else "-",
        "course_exam": task.course.exam_type if task and task.course else "-",
        "section_id": task.section_id if task else None,
        "section_number": task.section.number if task and task.section else None,
        "section_title": task.section.title if task and task.section else None,
        "topic_id": task.topic_id if task else None,
        "topic_title": task.topic.title if task and task.topic else None,
        "task_number": task.title if task else "-",
        "task_condition": task.condition_text if task else "",
        "max_score": task.max_score if task else 0,
        "file": _attempt_file_info(attempt),
        "solution_pages": _attempt_solution_pages_info(attempt),
        "ai_comment": latest_review.review_text if latest_review else "",
        "ai_recommendations": latest_review.recommendations if latest_review else "",
        "teacher_comment": latest_comment.comment_text if latest_comment else "",
        "teacher_status": latest_comment.status if latest_comment else display_status,
    }


def _teacher_attempt_detail(db: Session, attempt: models.Attempt) -> dict:
    task = attempt.task
    reviewer_id = _default_reviewer_id(db)
    history = (
        db.query(models.Attempt)
        .filter(models.Attempt.user_id == attempt.user_id)
        .filter(models.Attempt.task_id == attempt.task_id)
        .order_by(models.Attempt.attempt_number.asc(), models.Attempt.id.asc())
        .all()
    )
    return {
        "attempt": _teacher_attempt_summary(attempt),
        "student": {
            "id": attempt.user.id,
            "name": attempt.user.name,
            "email": attempt.user.email,
            "grade": attempt.user.grade,
            "target_exam": attempt.user.target_exam,
            "goal": attempt.user.goal,
        },
        "course": _course_to_read(db, task.course, attempt.user_id),
        "section": _section_to_read(task.section, db=db, user_id=attempt.user_id),
        "topic": _topic_to_read(task.topic, db=db, user_id=attempt.user_id),
        "task": {
            **_task_to_read(task, db=db, user_id=attempt.user_id),
            "condition_text": task.condition_text,
            "correct_answer": task.correct_answer,
            "criteria": task.criteria,
            "solution_explanation": task.solution_explanation,
            "material": _topic_material_to_read(_primary_topic_material(task.topic)),
        },
        "file": _attempt_file_info(attempt, reviewer_id),
        "solution_pages": _attempt_solution_pages_info(attempt, reviewer_id),
        "pipeline": [_pipeline_to_read(step) for step in attempt.pipeline_steps],
        "ai_reviews": [_review_to_read(review) for review in attempt.ai_reviews],
        "teacher_comments": [_teacher_comment_to_read(comment) for comment in attempt.teacher_comments],
        "history": [_teacher_attempt_history_item(item, reviewer_id) for item in history],
        "chat_history": _attempt_chat_history(db, attempt),
    }


def _teacher_attempt_history_item(attempt: models.Attempt, viewer_id: int | None = None) -> dict:
    latest_review = attempt.ai_reviews[-1] if attempt.ai_reviews else None
    return {
        **_attempt_to_read(attempt),
        "file": _attempt_file_info(attempt, viewer_id),
        "solution_pages": _attempt_solution_pages_info(attempt, viewer_id),
        "short_ai_comment": latest_review.review_text if latest_review else "",
    }


def _attempt_file_info(attempt: models.Attempt, viewer_id: int | None = None) -> dict | None:
    if not attempt.uploaded_file_path and not attempt.solution_pages:
        return None
    if attempt.uploaded_file_path:
        normalized_path = attempt.uploaded_file_path.replace("\\", "/").lstrip("/")
        name = attempt.uploaded_file_name or Path(normalized_path).name
        uploaded_at = attempt.committed_at or attempt.created_at
        url = _solution_file_url(attempt, viewer_id or attempt.user_id)
    else:
        first_page = attempt.solution_pages[0]
        normalized_path = first_page.file_path.replace("\\", "/").lstrip("/")
        name = first_page.original_filename
        uploaded_at = first_page.uploaded_at
        url = _solution_page_file_url(first_page, viewer_id or attempt.user_id)
    suffix = Path(normalized_path).suffix.lower()
    return {
        "path": normalized_path,
        "url": url,
        "download_url": f"{url}&download=1" if "?" in url else f"{url}?download=1",
        "name": name,
        "extension": suffix,
        "is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
        "is_pdf": suffix == ".pdf",
        "uploaded_at": uploaded_at,
    }


def _solution_file_url(attempt: models.Attempt, viewer_id: int | None = None) -> str:
    url = f"/solutions/{attempt.id}/file"
    if viewer_id:
        url += f"?viewer_id={viewer_id}"
    return url


def _task_reference_file_url(task: models.Task, viewer_id: int | None = None) -> str:
    url = f"/admin/tasks/{task.id}/reference-solution/file"
    if viewer_id:
        url += f"?viewer_id={viewer_id}"
    return url


def _task_reference_pages_info(task: models.Task, viewer_id: int | None = None) -> list[dict]:
    pages = list(task.reference_solution_pages or [])
    if pages:
        return [_task_reference_page_to_read(page, viewer_id) for page in pages]
    if not task.reference_solution_file_path:
        return []
    normalized_path = task.reference_solution_file_path.replace("\\", "/").lstrip("/")
    suffix = Path(normalized_path).suffix.lower()
    url = _task_reference_file_url(task, viewer_id)
    return [
        {
            "id": None,
            "task_id": task.id,
            "page_order": 1,
            "file_path": normalized_path,
            "original_filename": task.reference_solution_file_name or Path(normalized_path).name,
            "uploaded_at": None,
            "url": url,
            "download_url": f"{url}&download=1" if "?" in url else f"{url}?download=1",
            "extension": suffix,
            "is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
            "is_pdf": suffix == ".pdf",
        }
    ]


def _task_reference_page_to_read(page: models.TaskReferenceSolutionPage, viewer_id: int | None = None) -> dict:
    normalized_path = page.file_path.replace("\\", "/").lstrip("/")
    suffix = Path(normalized_path).suffix.lower()
    url = f"/admin/task-reference-pages/{page.id}/file"
    if viewer_id:
        url += f"?viewer_id={viewer_id}"
    return {
        "id": page.id,
        "task_id": page.task_id,
        "page_order": page.page_order,
        "file_path": normalized_path,
        "original_filename": page.original_filename,
        "uploaded_at": page.uploaded_at,
        "url": url,
        "download_url": f"{url}&download=1" if "?" in url else f"{url}?download=1",
        "extension": suffix,
        "is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
        "is_pdf": suffix == ".pdf",
    }


def _attempt_solution_pages_info(attempt: models.Attempt, viewer_id: int | None = None) -> list[dict]:
    pages = list(attempt.solution_pages or [])
    if pages:
        return [_solution_page_to_read(page, viewer_id or attempt.user_id) for page in pages]
    if not attempt.uploaded_file_path:
        return []
    normalized_path = attempt.uploaded_file_path.replace("\\", "/").lstrip("/")
    suffix = Path(normalized_path).suffix.lower()
    url = _solution_file_url(attempt, viewer_id or attempt.user_id)
    return [
        {
            "id": None,
            "attempt_id": attempt.id,
            "page_order": 1,
            "file_path": normalized_path,
            "original_filename": attempt.uploaded_file_name or Path(normalized_path).name,
            "uploaded_at": attempt.committed_at or attempt.created_at,
            "url": url,
            "download_url": f"{url}&download=1" if "?" in url else f"{url}?download=1",
            "extension": suffix,
            "is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
            "is_pdf": suffix == ".pdf",
        }
    ]


def _solution_page_to_read(page: models.AttemptSolutionPage, viewer_id: int | None = None) -> dict:
    normalized_path = page.file_path.replace("\\", "/").lstrip("/")
    suffix = Path(normalized_path).suffix.lower()
    url = _solution_page_file_url(page, viewer_id)
    return {
        "id": page.id,
        "attempt_id": page.attempt_id,
        "page_order": page.page_order,
        "file_path": normalized_path,
        "original_filename": page.original_filename,
        "uploaded_at": page.uploaded_at,
        "url": url,
        "download_url": f"{url}&download=1" if "?" in url else f"{url}?download=1",
        "extension": suffix,
        "is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
        "is_pdf": suffix == ".pdf",
    }


def _solution_page_file_url(page: models.AttemptSolutionPage, viewer_id: int | None = None) -> str:
    url = f"/solution-pages/{page.id}/file"
    if viewer_id:
        url += f"?viewer_id={viewer_id}"
    return url


def _static_asset_url(path: str | None) -> str | None:
    if not path:
        return None
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("static/"):
        return "/" + normalized
    return "/" + normalized


def _attempt_chat_history(db: Session, attempt: models.Attempt) -> dict:
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == attempt.user_id)
        .filter(
            (models.ChatSession.attempt_id == attempt.id)
            | (
                (models.ChatSession.attempt_id.is_(None))
                & (models.ChatSession.task_id == attempt.task_id)
            )
        )
        .order_by(models.ChatSession.id.desc())
        .limit(3)
        .all()
    )
    messages = []
    for session in reversed(sessions):
        for message in session.messages:
            messages.append(
                {
                    "id": message.id,
                    "session_id": session.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                }
            )
    return {
        "has_messages": bool(messages),
        "dialog_summary": sessions[0].summary if sessions else "",
        "messages": messages[-30:],
    }


def _pipeline_to_read(step: models.CheckPipelineStep) -> dict:
    return {
        "id": step.id,
        "attempt_id": step.attempt_id,
        "step_name": step.step_name,
        "status": step.status,
        "message": step.message,
        "created_at": step.created_at,
    }


def _review_to_read(review: models.AIReview | None) -> dict | None:
    if review is None:
        return None
    return {
        "id": review.id,
        "attempt_id": review.attempt_id,
        "agent_name": review.agent_name,
        "review_text": review.review_text,
        "mistakes": review.mistakes,
        "recommendations": review.recommendations,
        "quality_score": review.quality_score,
        "created_at": review.created_at,
    }


def _teacher_comment_to_read(comment: models.TeacherComment) -> dict:
    return {
        "id": comment.id,
        "attempt_id": comment.attempt_id,
        "teacher_id": comment.teacher_id,
        "comment_text": comment.comment_text,
        "final_score": comment.final_score,
        "status": comment.status,
        "created_at": comment.created_at,
    }
