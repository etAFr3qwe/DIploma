from __future__ import annotations

import re

from sqlalchemy.orm import Session

import models
from services.answer_checker import compare_answers
from services.ai_client import AIClient, AIClientFactory
from services.text_recognition import TextRecognitionAgent


class SolutionReviewAgent:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("solution_review")
        self.text_recognition = TextRecognitionAgent()

    def run_pipeline(self, db: Session, attempt: models.Attempt) -> models.AIReview:
        self._reset_pipeline(db, attempt)
        self._add_step(
            db,
            attempt,
            "Попытка получена",
            "success",
            (
                f"Попытка сохранена: загружено страниц/файлов решения — {len(attempt.solution_pages) or 1}."
                if attempt.uploaded_file_path or attempt.solution_pages
                else "Попытка сохранена: краткий ответ передан на автоматическую проверку."
            ),
        )

        if attempt.task.part == 2:
            recognized_text = ""
            attempt.recognized_text = ""
            self._add_step(
                db,
                attempt,
                "Распознавание текста",
                "manual_review",
                "Для заданий второй части OCR отключён: система сохраняет фото решения и передаёт страницы на ИИ-анализ или преподавателю.",
            )
            extracted_answer = ""
        else:
            recognized_text = self.text_recognition.recognize(attempt)
            attempt.recognized_text = recognized_text
            recognition_is_fallback = TextRecognitionAgent.is_fallback_text(recognized_text)
            ocr_warning = self._ocr_warning(recognized_text)
            recognition_status = (
                "manual_review"
                if recognition_is_fallback or ocr_warning
                else "success"
                if recognized_text
                else "manual_review"
            )
            self._add_step(
                db,
                attempt,
                "Текст решения распознан",
                recognition_status,
                self._recognition_message(recognized_text, ocr_warning),
            )

            can_extract_answer = bool(recognized_text) and not recognition_is_fallback
            extracted_answer = self.extract_answer(recognized_text) if can_extract_answer else ""
        attempt.extracted_answer = extracted_answer
        self._add_step(
            db,
            attempt,
            "Ответ извлечён",
            "success" if extracted_answer else "manual_review",
            f"Извлечённый ответ: {extracted_answer or 'не найден'}.",
        )

        check_result = compare_answers(extracted_answer, attempt.task.correct_answer) if extracted_answer and attempt.task.part == 1 else None
        correct = check_result.is_correct if check_result else None
        self._add_step(
            db,
            attempt,
            "Ответ нормализован",
            check_result.status if check_result else "manual_review",
            (
                f"Ответ ученика: {check_result.normalized_student or '-'}; "
                f"эталон: {check_result.normalized_correct or '-'}."
            )
            if check_result
            else "Для развёрнутого решения автоматическая нормализация краткого ответа не выполняется.",
        )
        attempt.is_correct = correct
        attempt.score = attempt.task.max_score if correct else 0 if correct is False else None
        self._add_step(
            db,
            attempt,
            "Ответ сравнен с эталоном",
            check_result.status if check_result else "manual_review",
            (
                (check_result.message + f" Эталон: {attempt.task.correct_answer}; ответ ученика: {extracted_answer or '-'}")
                if check_result
                else "Для заданий второй части правильный ответ ученику не показывается; преподаватель проверяет ход решения по файлу."
            ),
        )

        review = self._create_review(db, attempt, correct)
        self._add_step(db, attempt, "Решение проанализировано ИИ", "success", "Комментарий ИИ сохранён.")
        self._add_step(db, attempt, "Ошибки зафиксированы", "success", review.mistakes or "Существенных ошибок не найдено.")
        self._add_step(db, attempt, "Рекомендации сформированы", "success", review.recommendations)

        attempt.status = "проверено ИИ" if correct is not None else "manual_review"
        if attempt.pool_task:
            attempt.pool_task.status = attempt.status
        db.flush()
        return review

    @staticmethod
    def extract_answer(text: str | None) -> str:
        if not text:
            return ""
        lower_text = text.lower()
        answer_match = re.search(
            r"(?:ответ|ответы|answer|x\s*=)\s*[:=]?\s*([^\n]+)",
            lower_text,
        )
        if answer_match:
            candidate = answer_match.group(1).strip()
            candidate = re.split(r"(?:\. |\n|решени|провер)", candidate, maxsplit=1)[0]
            return candidate.strip(" .")
        math_tokens = re.findall(r"sqrt\([^)]+\)|\bpi\b|-?\d+\s*/\s*-?\d+|-?\d+(?:[,.]\d+)?", lower_text)
        return math_tokens[-1].replace(",", ".") if math_tokens else ""

    def _create_review(self, db: Session, attempt: models.Attempt, correct: bool | None) -> models.AIReview:
        previous_attempts = (
            db.query(models.Attempt)
            .filter(models.Attempt.user_id == attempt.user_id)
            .filter(models.Attempt.task_id == attempt.task_id)
            .filter(models.Attempt.id != attempt.id)
            .order_by(models.Attempt.id.asc())
            .all()
        )
        fallback = self._local_review(attempt, correct, previous_attempts)
        if attempt.task.part == 2:
            review_text = self.ai_client.analyze_solution_images(
                attempt.task,
                solution_file_paths=self._solution_file_paths(attempt),
                reference_file_path=getattr(attempt.task, "reference_solution_file_path", None),
                reference_file_paths=self._reference_solution_file_paths(attempt.task),
                criteria=attempt.task.criteria,
                attempt_history=previous_attempts,
                fallback=fallback["review_text"],
            )
        else:
            review_text = self.ai_client.analyze_solution(
                attempt.task,
                student_answer=None,
                recognized_text=attempt.recognized_text,
                criteria=attempt.task.criteria,
                attempt_history=previous_attempts,
                fallback=fallback["review_text"],
            )
        review_text = self._clean_review_text(review_text)
        review = models.AIReview(
            attempt_id=attempt.id,
            agent_name="SolutionReviewAgent",
            review_text=review_text,
            mistakes=self._mistakes_for_review(attempt, review_text, fallback["mistakes"]),
            recommendations=self._recommendations_for_review(attempt, review_text, fallback["recommendations"]),
            quality_score=fallback["quality_score"],
        )
        db.add(review)
        db.flush()
        return review

    @staticmethod
    def _local_review(attempt: models.Attempt, correct: bool | None, previous_attempts: list[models.Attempt]) -> dict:
        if attempt.task.part == 2 and correct is None:
            return {
                "review_text": (
                    "Решение второй части сохранено. Система анализирует загруженные страницы как фото, а итоговый балл выставляется "
                    "по полноте оформления, обоснованиям и правильности вывода."
                ),
                "mistakes": "Проверьте, достаточно ли понятно записаны преобразования, обоснования и итоговый ответ.",
                "recommendations": "Если какой-то фрагмент решения плохо читается, перепишите его крупнее и отправьте новую попытку.",
                "quality_score": 50,
            }
        if correct is True:
            return {
                "review_text": (
                    "Ответ совпадает с эталоном. По оформлению стоит явно записывать промежуточные шаги и проверку, "
                    "чтобы преподаватель видел ход рассуждений."
                ),
                "mistakes": "",
                "recommendations": "Решить одно похожее задание по таймеру, чтобы подтвердить устойчивость навыка.",
                "quality_score": 88 if previous_attempts else 82,
            }
        if correct is False:
            return {
                "review_text": (
                    "Ответ не совпадает с эталоном. Нужно проверить вычисления, оформление промежуточных шагов "
                    "и запись итогового ответа."
                ),
                "mistakes": f"Ошибка по теме «{attempt.task.topic.title}»: неверный итоговый ответ или неполная проверка.",
                "recommendations": "Повторить теорию по теме, затем решить 3 похожих задания с фиксацией времени.",
                "quality_score": 45,
            }
        return {
            "review_text": (
                "Автоматическая проверка не смогла уверенно извлечь ответ. Файл решения сохранён, "
                "преподаватель сможет посмотреть решение вручную."
            ),
            "mistakes": "Ответ не извлечён автоматически.",
            "recommendations": "Отправить новую попытку с более читаемым фото или PDF-файлом решения.",
            "quality_score": 35,
        }

    @staticmethod
    def _solution_file_paths(attempt: models.Attempt) -> list[str]:
        pages = sorted(attempt.solution_pages or [], key=lambda page: page.page_order or 0)
        paths = [page.file_path for page in pages if page.file_path]
        if not paths and attempt.uploaded_file_path:
            paths.append(attempt.uploaded_file_path)
        return paths

    @staticmethod
    def _reference_solution_file_paths(task: models.Task) -> list[str]:
        pages = sorted(task.reference_solution_pages or [], key=lambda page: page.page_order or 0)
        paths = [page.file_path for page in pages if page.file_path]
        if not paths and task.reference_solution_file_path:
            paths.append(task.reference_solution_file_path)
        return paths

    @staticmethod
    def _mistakes_for_review(attempt: models.Attempt, review_text: str, fallback: str) -> str:
        if attempt.task.part != 2:
            return fallback
        text = (review_text or "").lower()
        if "ошиб" in text or "не хватает" in text or "невер" in text or "исправ" in text:
            specific_issue = SolutionReviewAgent._specific_issue_from_review(review_text)
            if specific_issue:
                return specific_issue
            return "Проверьте строку решения, где сделан переход к итоговому ответу: там может не хватать обоснования, вычисления или пояснения."
        return "Критичных ошибок по фото не выделено. Финальный балл выставляет преподаватель по критериям."

    @staticmethod
    def _recommendations_for_review(attempt: models.Attempt, review_text: str, fallback: str) -> str:
        if attempt.task.part != 2:
            return fallback
        if "нечита" in (review_text or "").lower():
            return "Загрузите более читаемое фото или перепишите спорный фрагмент крупнее отдельной строкой."
        return "Сверьте решение с эталоном и критериями: должны быть видны все преобразования, обоснования и итоговый ответ."

    @staticmethod
    def _specific_issue_from_review(review_text: str | None) -> str:
        text = re.sub(r"\s+", " ", (review_text or "").replace("*", " ")).strip()
        if not text:
            return ""
        markers = (
            "не хватает",
            "ошиб",
            "невер",
            "исправ",
            "непонят",
            "нечит",
            "отсутств",
            "нужно добавить",
        )
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            lower_sentence = sentence.lower()
            if any(marker in lower_sentence for marker in markers):
                return sentence.strip()
        return ""

    @staticmethod
    def _ocr_warning(text: str | None) -> str:
        if not text or TextRecognitionAgent.is_fallback_text(text):
            return ""
        compact = " ".join(text.split())
        lower = compact.lower()
        suspicious_patterns = [
            r"\blatub\w*",
            r"\blatu\w*",
            r"\bat\s+\d",
            r"\b[a-z]{3,}\d+\s*=",
            r"[а-яё]\s+[a-z]{2,}\s+[а-яё]",
        ]
        if any(re.search(pattern, lower) for pattern in suspicious_patterns):
            if re.search(r"ответ|answer|latub|latu", lower):
                return "Похоже, OCR неуверенно распознал строку с итоговым ответом. Лучше переписать итоговую строку крупнее и отдельной строкой."
            return "Похоже, OCR неуверенно распознал один из фрагментов решения. Лучше переписать спорную строку крупнее и без сокращений."
        latin_fragments = re.findall(r"\b[a-zA-Z]{2,}\w*\b", compact)
        if len(latin_fragments) >= 2:
            return "В распознанном тексте есть несколько латинских фрагментов вместо математических записей. Проверьте строки с формулами и итоговым ответом."
        return ""

    @staticmethod
    def _recognition_message(text: str | None, warning: str) -> str:
        if not text:
            return "Текст не найден. Преподаватель сможет проверить загруженный файл вручную."
        if warning:
            return f"{warning}\n\nРаспознанный текст для преподавателя:\n{text}"
        return text

    @staticmethod
    def _clean_review_text(text: str | None) -> str:
        cleaned = (text or "").strip()
        replacements = {
            "\\cdot": "·",
            "\\times": "·",
            "\\left": "",
            "\\right": "",
            "\\(": "(",
            "\\)": ")",
            "\\[": "",
            "\\]": "",
            "$": "",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        cleaned = re.sub(r"[*`#_]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or "Решение принято к проверке. Преподаватель сможет оценить ход решения по загруженному файлу."

    def _reset_pipeline(self, db: Session, attempt: models.Attempt) -> None:
        for step in list(attempt.pipeline_steps):
            db.delete(step)
        db.flush()

    @staticmethod
    def _add_step(db: Session, attempt: models.Attempt, name: str, status: str, message: str) -> None:
        db.add(
            models.CheckPipelineStep(
                attempt_id=attempt.id,
                step_name=name,
                status=status,
                message=message,
            )
        )
