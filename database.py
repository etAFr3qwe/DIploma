import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./exam_preparation.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_database_schema() -> None:
    """Create database tables for the exam preparation platform."""
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "teacher_comments" not in table_names:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("teacher_comments")}
    statements = []
    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "password" not in user_columns:
            statements.append("ALTER TABLE users ADD COLUMN password VARCHAR(128) NOT NULL DEFAULT 'password'")

    if "final_score" not in existing_columns:
        statements.append("ALTER TABLE teacher_comments ADD COLUMN final_score FLOAT")
    if "status" not in existing_columns:
        statements.append(
            "ALTER TABLE teacher_comments ADD COLUMN status VARCHAR(60) NOT NULL DEFAULT 'проверено преподавателем'"
        )

    if "tasks" in table_names:
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "solution_video_url" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN solution_video_url VARCHAR(500)")
        if "exam_type" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN exam_type VARCHAR(40) NOT NULL DEFAULT ''")
        if "part" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN part INTEGER NOT NULL DEFAULT 1")
        if "task_number" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN task_number INTEGER")
        if "prototype_number" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN prototype_number VARCHAR(40)")
        if "analog_number" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN analog_number VARCHAR(40)")
        if "bank_topic" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN bank_topic VARCHAR(220)")
        if "image_path" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN image_path VARCHAR(500)")
        if "context_image_path" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN context_image_path VARCHAR(500)")
        if "answer" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN answer TEXT")
        if "solution" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN solution TEXT")
        if "reference_solution_file_path" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN reference_solution_file_path VARCHAR(500)")
        if "reference_solution_file_name" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN reference_solution_file_name VARCHAR(255)")
        if "source_file" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN source_file VARCHAR(255)")
        if "source_page" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN source_page INTEGER")
        if "is_active" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
        if "task_type" not in task_columns:
            statements.append(
                "ALTER TABLE tasks ADD COLUMN task_type VARCHAR(160) NOT NULL DEFAULT 'экзаменационное задание'"
            )
        if "answer_format" not in task_columns:
            statements.append("ALTER TABLE tasks ADD COLUMN answer_format VARCHAR(80) NOT NULL DEFAULT 'краткий ответ'")

    if "chat_sessions" in table_names:
        chat_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
        if "attempt_id" not in chat_columns:
            statements.append("ALTER TABLE chat_sessions ADD COLUMN attempt_id INTEGER")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
