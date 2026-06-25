from __future__ import annotations

from pathlib import Path

import models
from services.ai_client import AIClient, AIClientFactory


FALLBACK_MARKERS = (
    "локальном тестовом режиме",
    "недоступно",
    "не выполнено",
    "не удалось распознать",
    "не вернул текст",
    "не найден",
    "файл решения сохранён",
    "ошибка yandex ocr",
    "распознавание через",
    "причина:",
)


class TextRecognitionAgent:
    """Распознаёт текст из загруженного решения или возвращает безопасный fallback."""

    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("text_recognition")

    def recognize(self, attempt: models.Attempt) -> str:
        pages = sorted(list(attempt.solution_pages or []), key=lambda page: page.page_order or page.id)
        if attempt.student_text_answer and not attempt.uploaded_file_path and not pages:
            return f"Ответ: {attempt.student_text_answer.strip()}"

        file_paths = [page.file_path for page in pages if page.file_path]
        if not file_paths and attempt.uploaded_file_path:
            file_paths = [attempt.uploaded_file_path]
        if not file_paths:
            return ""

        recognized_pages = []
        for index, file_path in enumerate(file_paths, start=1):
            recognized = self.ai_client.recognize_text_from_file(file_path)
            if recognized:
                prefix = f"Страница {index}. " if len(file_paths) > 1 else ""
                recognized_pages.append(f"{prefix}{recognized}".strip())
        if recognized_pages:
            return "\n\n".join(recognized_pages)

        extension = Path(file_paths[0]).suffix.lower()
        page_note = f" Загружено страниц/файлов: {len(pages)}." if len(pages) > 1 else ""
        if extension in {".jpg", ".jpeg", ".png", ".pdf"}:
            provider = self.ai_client.provider_name
            return f"Файл решения сохранён.{page_note} Распознавание через {provider} не вернуло текст."
        return f"Файл решения сохранён.{page_note} Текст не удалось распознать автоматически."

    @staticmethod
    def is_fallback_text(text: str | None) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in FALLBACK_MARKERS)
