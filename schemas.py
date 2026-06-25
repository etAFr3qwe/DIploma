from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


UserRole = Literal["Student", "Teacher", "Parent", "Admin"]
ExamType = Literal["ОГЭ", "ЕГЭ"]
PoolPeriod = Literal["день", "неделя", "месяц"]


class HealthResponse(BaseModel):
    status: str
    message: str


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: UserRole = "Student"
    email: EmailStr
    password: str = "password"
    grade: str = "9 класс"
    target_exam: ExamType | str = "ОГЭ"
    goal: str = "подготовка к экзамену"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    email: EmailStr
    grade: str
    target_exam: str
    goal: str
    created_at: datetime


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    exam_type: str
    description: str
    format_with_teacher_price: float
    format_ai_price: float
    section_count: int = 0
    topic_count: int = 0
    task_count: int = 0
    completed_tasks: int = 0
    average_time_seconds: float = 0
    correct_percent: float = 0
    predicted_score: float = 0
    readiness_percent: float = 0
    created_at: datetime


class ExamSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    number: int
    title: str
    description: str
    max_score: float
    topic_count: int = 0
    task_count: int = 0
    completion_percent: float = 0
    average_result_percent: float = 0


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    course_id: int
    title: str
    theory_content: str
    examples: str
    difficulty: str
    task_count: int = 0
    mastery_percent: float = 0
    material: dict[str, Any] | None = None


class TopicMaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    title: str
    content: str
    examples: str
    created_at: datetime
    updated_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    section_id: int
    course_id: int
    title: str
    condition_text: str
    correct_answer: str
    solution_explanation: str
    material: dict[str, Any] | None = None
    exam_type: str = ""
    part: int = 1
    task_number: int | None = None
    prototype_number: str | None = None
    analog_number: str | None = None
    bank_topic: str | None = None
    image_path: str | None = None
    image_url: str | None = None
    context_image_path: str | None = None
    context_image_url: str | None = None
    answer: str | None = None
    solution: str | None = None
    reference_solution_file_path: str | None = None
    reference_solution_file_name: str | None = None
    reference_solution_file_url: str | None = None
    reference_solution_pages: list[dict[str, Any]] = Field(default_factory=list)
    source_file: str | None = None
    source_page: int | None = None
    is_active: bool = True
    task_type: str = "экзаменационное задание"
    answer_format: str = "краткий ответ"
    criteria: str
    difficulty: str
    max_score: float
    section_number: int | None = None
    section_title: str | None = None
    topic_title: str | None = None
    course_title: str | None = None
    status: str = "не начато"
    average_time_seconds: float = 0
    attempts_count: int = 0


class CourseDetailRead(CourseRead):
    sections: list[ExamSectionRead] = Field(default_factory=list)
    topics: list[TopicRead] = Field(default_factory=list)
    first_tasks: list[TaskRead] = Field(default_factory=list)


class AssignmentPoolCreate(BaseModel):
    course_id: int
    title: str = "План на неделю"
    period: PoolPeriod = "неделя"
    task_ids: list[int] = Field(default_factory=list)
    deadline: datetime | None = None


class PoolTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pool_id: int
    task_id: int
    status: str
    deadline: datetime | None = None
    module: str | None = None
    topic: str | None = None
    attempts_count: int = 0
    average_time_seconds: float = 0
    result: str = "-"
    task: TaskRead | None = None


class AssignmentPoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_id: int
    title: str
    period_start: datetime
    period_end: datetime
    deadline: datetime
    status: str
    completion_percent: float = 0
    course_title: str | None = None
    pool_tasks: list[PoolTaskRead] = Field(default_factory=list)


class AttemptStartRequest(BaseModel):
    user_id: int
    pool_task_id: int | None = None


class AttemptCommitResponse(BaseModel):
    attempt: dict[str, Any]
    pipeline: list[dict[str, Any]]
    review: dict[str, Any] | None
    duration_seconds: int | None = None
    status: str | None = None


class SolutionPageRead(BaseModel):
    id: int | None = None
    attempt_id: int
    page_order: int
    file_path: str
    original_filename: str
    uploaded_at: datetime | None = None
    url: str | None = None
    download_url: str | None = None
    extension: str | None = None
    is_image: bool = False
    is_pdf: bool = False


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    user_id: int
    task_id: int
    pool_task_id: int | None
    attempt_number: int
    started_at: datetime
    committed_at: datetime | None
    duration_seconds: int | None
    uploaded_file_path: str | None
    uploaded_file_name: str | None
    student_text_answer: str | None
    recognized_text: str | None
    extracted_answer: str | None
    is_correct: bool | None
    score: float | None
    status: str
    created_at: datetime
    task_title: str | None = None
    course_id: int | None = None
    course_title: str | None = None
    section_title: str | None = None
    topic_title: str | None = None
    file_url: str | None = None
    solution_pages: list[SolutionPageRead] = Field(default_factory=list)
    solution_pages_count: int = 0
    task_condition: str | None = None
    correct_answer: str | None = None
    criteria: str | None = None


class PipelineStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    step_name: str
    status: str
    message: str
    created_at: datetime


class AIReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    agent_name: str
    review_text: str
    mistakes: str
    recommendations: str
    quality_score: float
    created_at: datetime


class TeacherCommentCreate(BaseModel):
    teacher_id: int
    comment_text: str = Field(min_length=2)
    final_score: float | None = None
    status: str = "проверено преподавателем"


class TeacherAttemptStatusUpdate(BaseModel):
    status: str
    score: float | None = None


class TaskReferenceSolutionUpdate(BaseModel):
    teacher_id: int
    reference_solution: str = Field(min_length=5)
    correct_answer: str | None = None
    criteria: str | None = None


class TaskAdminCreate(BaseModel):
    admin_id: int
    course_id: int
    section_id: int
    topic_id: int
    title: str = Field(min_length=2)
    condition_text: str = Field(min_length=2)
    correct_answer: str = ""
    criteria: str = "Проверяется администратором по эталонному решению."
    part: int = 1
    task_number: int | None = None
    difficulty: str = "базовый"
    max_score: float = 1


class TeacherCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    teacher_id: int
    comment_text: str
    final_score: float | None = None
    status: str
    created_at: datetime


class AIChatRequest(BaseModel):
    user_id: int
    message: str = Field(min_length=2)
    course_id: int | None = None
    topic_id: int | None = None
    task_id: int | None = None
    attempt_id: int | None = None


class AIChatResponse(BaseModel):
    user_id: int
    session_id: int
    answer: str
    allowed: bool = True
    detected_topic: str = ""
    summary_used: bool = False
    dialog_summary_used: bool = False
    recommendations: list[str] = Field(default_factory=list)


class TopicGuardRequest(BaseModel):
    message: str
    course_id: int | None = None
    topic_id: int | None = None
    task_id: int | None = None


class TopicGuardResponse(BaseModel):
    allowed: bool
    reason: str
    detected_topic: str


class SimilarTasksResponse(BaseModel):
    source_task_id: int
    tasks: list[dict[str, Any]]


class AnalyticsRead(BaseModel):
    user_id: int
    course_id: int
    completion_percent: float
    correct_percent: float
    attempts_count: int
    average_time_seconds: float
    average_time_by_type: dict[str, float]
    first_try_success_percent: float
    mastered_task_types_count: int
    stability_percent: float
    errors_by_topic: dict[str, int]
    predicted_primary_score: float
    predicted_test_score: float
    predicted_grade: str
    risk_level: str
    risks: list[str]


class ForecastRead(BaseModel):
    user_id: int
    course_id: int
    expected_primary_score: float
    expected_test_score: float
    predicted_grade: str
    risk_level: str
    weak_topics: list[str]
    strong_topics: list[str]
    weekly_focus: list[str]
    confidence_percent: float


class ParentReportRead(BaseModel):
    user_id: int
    student_name: str
    current_level: str
    completed_tasks: int
    attempts_count: int
    average_time_seconds: float
    correct_percent: float
    predicted_primary_score: float
    predicted_test_score: float
    main_risks: list[str]
    real_activity: list[str]
    weak_topics: list[str]
    mastered_topics: list[str]
    next_week_recommendations: list[str]


class TeacherDashboardRead(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    students: list[dict[str, Any]]
    attempts_for_review: list[dict[str, Any]]
    recent_attempts: list[dict[str, Any]]
    forecasts: list[dict[str, Any]]


class PurchaseRequestCreate(BaseModel):
    user_id: int
    course_id: int
    tariff_type: Literal["teacher", "ai"]


class PurchaseRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_id: int
    tariff_type: str
    status: str
    created_at: datetime
    message: str | None = None


class TrainResponse(BaseModel):
    samples: int
    accuracy: float
    roc_auc: float | None
    test_loss: float
    message: str
