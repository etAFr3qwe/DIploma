from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False, default="Student")
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(128), nullable=False, default="password")
    grade = Column(String(20), nullable=False, default="9 класс")
    target_exam = Column(String(20), nullable=False, default="ОГЭ")
    goal = Column(String(255), nullable=False, default="подготовка к экзамену")
    created_at = Column(DateTime, default=datetime.utcnow)

    assignment_pools = relationship("AssignmentPool", back_populates="user", cascade="all, delete-orphan")
    attempts = relationship("Attempt", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    analytics_snapshots = relationship("AnalyticsSnapshot", back_populates="user", cascade="all, delete-orphan")
    purchase_requests = relationship("PurchaseRequest", back_populates="user", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, unique=True)
    exam_type = Column(String(20), nullable=False, index=True)
    description = Column(Text, nullable=False)
    format_with_teacher_price = Column(Float, nullable=False, default=0)
    format_ai_price = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    sections = relationship(
        "ExamSection",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="ExamSection.number",
    )
    topics = relationship("Topic", back_populates="course")
    tasks = relationship("Task", back_populates="course")
    assignment_pools = relationship("AssignmentPool", back_populates="course")
    purchase_requests = relationship("PurchaseRequest", back_populates="course")

    @property
    def section_count(self) -> int:
        return len(self.sections)

    @property
    def task_count(self) -> int:
        return len(self.tasks)


class ExamSection(Base):
    __tablename__ = "exam_sections"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    title = Column(String(220), nullable=False)
    description = Column(Text, nullable=False)
    max_score = Column(Float, nullable=False, default=1)

    course = relationship("Course", back_populates="sections")
    topics = relationship(
        "Topic",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="Topic.id",
    )
    tasks = relationship("Task", back_populates="section")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("exam_sections.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    theory_content = Column(Text, nullable=False)
    examples = Column(Text, nullable=False, default="")
    difficulty = Column(String(40), nullable=False, default="базовый")

    section = relationship("ExamSection", back_populates="topics")
    course = relationship("Course", back_populates="topics")
    materials = relationship(
        "TopicMaterial",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TopicMaterial.id",
    )
    tasks = relationship(
        "Task",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="Task.id",
    )


class TopicMaterial(Base):
    __tablename__ = "topic_materials"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    content = Column(Text, nullable=False)
    examples = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="materials")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("exam_sections.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    condition_text = Column(Text, nullable=False)
    correct_answer = Column(String(255), nullable=False)
    solution_explanation = Column(Text, nullable=False)
    solution_video_url = Column(String(500), nullable=True)
    exam_type = Column(String(40), nullable=False, default="")
    part = Column(Integer, nullable=False, default=1)
    task_number = Column(Integer, nullable=True, index=True)
    prototype_number = Column(String(40), nullable=True)
    analog_number = Column(String(40), nullable=True)
    bank_topic = Column(String(220), nullable=True)
    image_path = Column(String(500), nullable=True)
    context_image_path = Column(String(500), nullable=True)
    answer = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    reference_solution_file_path = Column(String(500), nullable=True)
    reference_solution_file_name = Column(String(255), nullable=True)
    source_file = Column(String(255), nullable=True)
    source_page = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    task_type = Column(String(160), nullable=False, default="экзаменационное задание")
    answer_format = Column(String(80), nullable=False, default="краткий ответ")
    criteria = Column(Text, nullable=False)
    difficulty = Column(String(40), nullable=False, default="базовый")
    max_score = Column(Float, nullable=False, default=1)

    topic = relationship("Topic", back_populates="tasks")
    section = relationship("ExamSection", back_populates="tasks")
    course = relationship("Course", back_populates="tasks")
    pool_tasks = relationship("PoolTask", back_populates="task")
    attempts = relationship("Attempt", back_populates="task", cascade="all, delete-orphan")
    reference_solution_pages = relationship(
        "TaskReferenceSolutionPage",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskReferenceSolutionPage.page_order",
    )


class TaskReferenceSolutionPage(Base):
    __tablename__ = "task_reference_solution_pages"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    page_order = Column(Integer, nullable=False, default=1)
    original_filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="reference_solution_pages")


class AssignmentPool(Base):
    __tablename__ = "assignment_pools"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    title = Column(String(220), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    deadline = Column(DateTime, nullable=False)
    status = Column(String(40), nullable=False, default="не начато")

    user = relationship("User", back_populates="assignment_pools")
    course = relationship("Course", back_populates="assignment_pools")
    pool_tasks = relationship(
        "PoolTask",
        back_populates="pool",
        cascade="all, delete-orphan",
        order_by="PoolTask.id",
    )

    @property
    def completion_percent(self) -> float:
        if not self.pool_tasks:
            return 0.0
        completed_statuses = {
            "отправлено",
            "проверено",
            "проверено ИИ",
            "проверено преподавателем",
            "исправлено",
            "зачтено",
            "не зачтено",
            "требуется исправление",
            "нужна ручная проверка",
        }
        completed = sum(1 for item in self.pool_tasks if item.status in completed_statuses)
        return round(completed / len(self.pool_tasks) * 100, 1)


class PoolTask(Base):
    __tablename__ = "pool_tasks"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("assignment_pools.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="не начато")

    pool = relationship("AssignmentPool", back_populates="pool_tasks")
    task = relationship("Task", back_populates="pool_tasks")
    attempts = relationship("Attempt", back_populates="pool_task")


class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    pool_task_id = Column(Integer, ForeignKey("pool_tasks.id"), nullable=True, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    committed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    uploaded_file_path = Column(String(500), nullable=True)
    uploaded_file_name = Column(String(255), nullable=True)
    student_text_answer = Column(Text, nullable=True)
    recognized_text = Column(Text, nullable=True)
    extracted_answer = Column(String(255), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)
    status = Column(String(40), nullable=False, default="в работе")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="attempts")
    task = relationship("Task", back_populates="attempts")
    pool_task = relationship("PoolTask", back_populates="attempts")
    pipeline_steps = relationship(
        "CheckPipelineStep",
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="CheckPipelineStep.id",
    )
    solution_pages = relationship(
        "AttemptSolutionPage",
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="AttemptSolutionPage.page_order",
    )
    ai_reviews = relationship("AIReview", back_populates="attempt", cascade="all, delete-orphan")
    teacher_comments = relationship("TeacherComment", back_populates="attempt", cascade="all, delete-orphan")


class AttemptSolutionPage(Base):
    __tablename__ = "attempt_solution_pages"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    page_order = Column(Integer, nullable=False, default=1)
    original_filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    attempt = relationship("Attempt", back_populates="solution_pages")


class CheckPipelineStep(Base):
    __tablename__ = "check_pipeline_steps"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False, index=True)
    step_name = Column(String(120), nullable=False)
    status = Column(String(60), nullable=False, default="pending")
    message = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    attempt = relationship("Attempt", back_populates="pipeline_steps")


class AIReview(Base):
    __tablename__ = "ai_reviews"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False, index=True)
    agent_name = Column(String(80), nullable=False)
    review_text = Column(Text, nullable=False)
    mistakes = Column(Text, nullable=False, default="")
    recommendations = Column(Text, nullable=False, default="")
    quality_score = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    attempt = relationship("Attempt", back_populates="ai_reviews")


class TeacherComment(Base):
    __tablename__ = "teacher_comments"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    comment_text = Column(Text, nullable=False)
    final_score = Column(Float, nullable=True)
    status = Column(String(60), nullable=False, default="проверено преподавателем")
    created_at = Column(DateTime, default=datetime.utcnow)

    attempt = relationship("Attempt", back_populates="teacher_comments")
    teacher = relationship("User")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=True, index=True)
    summary = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_sessions")
    course = relationship("Course")
    topic = relationship("Topic")
    task = relationship("Task")
    attempt = relationship("Attempt")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    completion_percent = Column(Float, nullable=False, default=0)
    correct_percent = Column(Float, nullable=False, default=0)
    average_time_seconds = Column(Float, nullable=False, default=0)
    first_try_success_percent = Column(Float, nullable=False, default=0)
    mastered_task_types_count = Column(Integer, nullable=False, default=0)
    predicted_primary_score = Column(Float, nullable=False, default=0)
    predicted_test_score = Column(Float, nullable=False, default=0)
    predicted_grade = Column(String(20), nullable=False, default="-")
    risk_level = Column(String(40), nullable=False, default="средний")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="analytics_snapshots")
    course = relationship("Course")


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    tariff_type = Column(String(80), nullable=False)
    status = Column(String(40), nullable=False, default="создана")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="purchase_requests")
    course = relationship("Course", back_populates="purchase_requests")
