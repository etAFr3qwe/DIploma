from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pdfplumber
from pdf2image import convert_from_path
from PIL import Image


EXAM_CONFIG = {
    "OGE": {
        "course_title": "Подготовка к ОГЭ по математике",
        "course_exam_type": "ОГЭ",
        "manifest_dir": "oge",
        "answer_start_hint": "ОТВЕТЫ",
        "numbers": {
            1: ("Часть 1. №1. Практико-ориентированная задача", "Практико-ориентированные задачи", 1, 1),
            2: ("Часть 1. №2. Практико-ориентированная задача", "Практико-ориентированные задачи", 1, 1),
            3: ("Часть 1. №3. Практико-ориентированная задача", "Практико-ориентированные задачи", 1, 1),
            4: ("Часть 1. №4. Практико-ориентированная задача", "Практико-ориентированные задачи", 1, 1),
            5: ("Часть 1. №5. Практико-ориентированная задача", "Практико-ориентированные задачи", 1, 1),
            6: ("Часть 1. №6. Числа и вычисления", "Числа и вычисления", 1, 1),
            7: ("Часть 1. №7. Координатная прямая", "Координатная прямая", 1, 1),
            8: ("Часть 1. №8. Степени и корни", "Степени и корни", 1, 1),
            9: ("Часть 1. №9. Уравнения", "Уравнения", 1, 1),
            10: ("Часть 1. №10. Вероятность", "Вероятность", 1, 1),
            11: ("Часть 1. №11. Графики функций", "Графики функций", 1, 1),
            12: ("Часть 1. №12. Функции", "Функции", 1, 1),
            13: ("Часть 1. №13. Неравенства", "Неравенства", 1, 1),
            14: ("Часть 1. №14. Последовательности", "Последовательности и прогрессии", 1, 1),
            15: ("Часть 1. №15. Геометрия", "Геометрия", 1, 1),
            16: ("Часть 1. №16. Геометрия", "Геометрия", 1, 1),
            17: ("Часть 1. №17. Геометрия", "Геометрия", 1, 1),
            18: ("Часть 1. №18. Геометрия", "Геометрия", 1, 1),
            19: ("Часть 1. №19. Анализ утверждений", "Геометрия и анализ утверждений", 1, 1),
            20: ("Часть 2. №20. Выражения, уравнения и неравенства", "Выражения, уравнения и неравенства", 2, 2),
            21: ("Часть 2. №21. Текстовые задачи", "Текстовые задачи", 2, 2),
            22: ("Часть 2. №22. Построение графиков функций", "Построение графиков функций", 2, 2),
            23: ("Часть 2. №23. Геометрическая задача на вычисление", "Геометрические задачи на вычисление", 2, 2),
            24: ("Часть 2. №24. Геометрическая задача на доказательство", "Геометрические задачи на доказательство", 2, 2),
            25: ("Часть 2. №25. Геометрическая задача повышенной сложности", "Геометрические задачи повышенной сложности", 2, 2),
        },
    },
    "EGE_PROFILE": {
        "course_title": "Подготовка к ЕГЭ по математике",
        "course_exam_type": "ЕГЭ",
        "manifest_dir": "ege_profile",
        "answer_start_hint": "ОТВЕТЫ",
        "numbers": {
            1: ("Часть 1. №1. Планиметрия", "Планиметрия", 1, 1),
            2: ("Часть 1. №2. Векторы", "Векторы", 1, 1),
            3: ("Часть 1. №3. Стереометрия", "Стереометрия", 1, 1),
            4: ("Часть 1. №4. Вероятность", "Вероятность", 1, 1),
            5: ("Часть 1. №5. Вероятность", "Вероятность", 1, 1),
            6: ("Часть 1. №6. Уравнения", "Уравнения", 1, 1),
            7: ("Часть 1. №7. Вычисления и преобразования", "Вычисления и преобразования", 1, 1),
            8: ("Часть 1. №8. Производная", "Производная и исследование функций", 1, 1),
            9: ("Часть 1. №9. Прикладные задачи", "Прикладные задачи", 1, 1),
            10: ("Часть 1. №10. Текстовые задачи", "Текстовые задачи", 1, 1),
            11: ("Часть 1. №11. Графики и функции", "Графики и функции", 1, 1),
            12: ("Часть 1. №12. Экстремумы", "Экстремумы", 1, 1),
            13: ("Часть 2. №13. Уравнения", "Уравнения", 2, 2),
            14: ("Часть 2. №14. Стереометрия", "Стереометрия", 2, 2),
            15: ("Часть 2. №15. Неравенства", "Неравенства", 2, 2),
            16: ("Часть 2. №16. Финансовые задачи", "Финансовая математика", 2, 2),
            17: ("Часть 2. №17. Планиметрия", "Планиметрия", 2, 2),
            18: ("Часть 2. №18. Параметры", "Задачи с параметром", 2, 2),
            19: ("Часть 2. №19. Нестандартные задачи", "Нестандартные задачи", 2, 2),
        },
    },
}


TASK_MARKER_RE = re.compile(r"Задача\s+(\d+)[\.,](\d+(?:\.\d+)*)", re.IGNORECASE)
ANSWER_LINE_RE = re.compile(r"№\s*(\d+)[\.,](\d+(?:\.\d+)*)\s+(.+?)(?=\s+№\s*\d+[\.,]\d+|$)")


@dataclass
class Marker:
    task_number: int
    analog_number: str
    page_index: int
    top: float
    bottom: float
    text: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт банка задач ОГЭ/ЕГЭ из PDF в изображения и SQLite.")
    parser.add_argument("--file", required=True, help="Путь к PDF-файлу банка заданий.")
    parser.add_argument("--exam", required=True, choices=sorted(EXAM_CONFIG), help="Тип экзамена: OGE или EGE_PROFILE.")
    parser.add_argument("--max-per-number", type=int, default=2, help="Сколько аналогов брать для каждого номера экзамена.")
    parser.add_argument("--dpi", type=int, default=180, help="DPI для изображений заданий.")
    parser.add_argument("--replace", action="store_true", help="Удалить ранее импортированные задания этого экзамена из БД.")
    parser.add_argument("--manifest-only", action="store_true", help="Создать только manifest и изображения, не писать в БД.")
    parser.add_argument("--poppler-path", default=None, help="Путь к bin Poppler, если pdftoppm не в PATH.")
    args = parser.parse_args()

    import_pdf_bank(
        pdf_path=Path(args.file),
        exam=args.exam,
        max_per_number=args.max_per_number,
        dpi=args.dpi,
        replace=args.replace,
        manifest_only=args.manifest_only,
        poppler_path=args.poppler_path,
    )
    return 0


def import_pdf_bank(
    pdf_path: Path,
    exam: str,
    max_per_number: int = 2,
    dpi: int = 180,
    replace: bool = False,
    manifest_only: bool = False,
    poppler_path: str | None = None,
) -> dict:
    if exam not in EXAM_CONFIG:
        raise ValueError(f"Неизвестный экзамен: {exam}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF не найден: {pdf_path}")

    config = EXAM_CONFIG[exam]
    output_dir = ROOT_DIR / "static" / "imported_tasks" / config["manifest_dir"]
    context_dir = output_dir / "contexts"
    output_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)

    answers = _extract_answers(pdf_path)
    tasks = _extract_task_images(
        pdf_path=pdf_path,
        exam=exam,
        output_dir=output_dir,
        context_dir=context_dir,
        answers=answers,
        max_per_number=max_per_number,
        dpi=dpi,
        poppler_path=poppler_path or _default_poppler_path(),
    )
    manifest = {
        "exam": exam,
        "source_file": pdf_path.name,
        "course_title": config["course_title"],
        "course_exam_type": config["course_exam_type"],
        "imported_at": _now_iso(),
        "tasks": tasks,
    }
    manifest_path = ROOT_DIR / "data" / "imported_banks" / config["manifest_dir"] / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not manifest_only:
        from database import SessionLocal, ensure_database_schema

        ensure_database_schema()
        db = SessionLocal()
        try:
            write_manifest_to_db(db, manifest, replace_exam=replace)
            db.commit()
        finally:
            db.close()

    print(f"Импортировано заданий {exam}: {len(tasks)}")
    print(f"Manifest: {manifest_path}")
    return manifest


def write_manifest_to_db(db, manifest: dict, replace_exam: bool = False) -> None:
    import models

    exam = manifest["exam"]
    config = EXAM_CONFIG[exam]
    course = db.query(models.Course).filter(models.Course.title == config["course_title"]).first()
    if course is None:
        course = models.Course(
            title=config["course_title"],
            exam_type=config["course_exam_type"],
            description=f"Курс сформирован на основе PDF-банка заданий: {manifest['source_file']}.",
            format_with_teacher_price=0,
            format_ai_price=0,
        )
        db.add(course)
        db.flush()

    if replace_exam:
        for task in list(db.query(models.Task).filter(models.Task.course_id == course.id).all()):
            db.delete(task)
        for topic in list(db.query(models.Topic).filter(models.Topic.course_id == course.id).all()):
            db.delete(topic)
        for section in list(db.query(models.ExamSection).filter(models.ExamSection.course_id == course.id).all()):
            db.delete(section)
        db.flush()

    sections: dict[int, models.ExamSection] = {}
    topics: dict[tuple[int, str], models.Topic] = {}
    for item in manifest["tasks"]:
        section = _ensure_section(db, course, item, sections)
        topic = _ensure_topic(db, course, section, item, topics)
        existing = (
            db.query(models.Task)
            .filter(models.Task.course_id == course.id)
            .filter(models.Task.exam_type == exam)
            .filter(models.Task.task_number == item["task_number"])
            .filter(models.Task.analog_number == item["analog_number"])
            .first()
        )
        if existing is None:
            existing = models.Task(course_id=course.id, section_id=section.id, topic_id=topic.id, title=item["title"])
            db.add(existing)
        existing.section_id = section.id
        existing.topic_id = topic.id
        existing.title = item["title"]
        existing.condition_text = item["condition_text"]
        existing.correct_answer = item.get("answer") or ""
        existing.solution_explanation = item.get("solution") or "Решение/критерии берутся из банка заданий при наличии ответа."
        existing.solution_video_url = None
        existing.exam_type = exam
        existing.part = item["part"]
        existing.task_number = item["task_number"]
        existing.prototype_number = item.get("prototype_number")
        existing.analog_number = item["analog_number"]
        existing.bank_topic = item["topic"]
        existing.image_path = item["image_path"]
        existing.context_image_path = item.get("context_image_path")
        existing.answer = item.get("answer")
        existing.solution = item.get("solution")
        existing.source_file = item["source_file"]
        existing.source_page = item["source_page"]
        existing.is_active = True
        existing.task_type = item["task_type"]
        existing.answer_format = item["answer_format"]
        existing.criteria = item["criteria"]
        existing.difficulty = item["difficulty"]
        existing.max_score = item["max_score"]
    db.flush()


def _ensure_section(db, course: models.Course, item: dict, cache: dict[int, models.ExamSection]) -> models.ExamSection:
    import models

    task_number = int(item["task_number"])
    if task_number in cache:
        return cache[task_number]
    section = (
        db.query(models.ExamSection)
        .filter(models.ExamSection.course_id == course.id)
        .filter(models.ExamSection.number == task_number)
        .first()
    )
    if section is None:
        section = models.ExamSection(
            course_id=course.id,
            number=task_number,
            title=item["section_title"],
            description=f"{item['section_title']}. Задания импортированы из PDF-банка.",
            max_score=item["max_score"],
        )
        db.add(section)
        db.flush()
    else:
        section.title = item["section_title"]
        section.description = f"{item['section_title']}. Задания импортированы из PDF-банка."
        section.max_score = item["max_score"]
    cache[task_number] = section
    return section


def _ensure_topic(db, course: models.Course, section: models.ExamSection, item: dict, cache: dict[tuple[int, str], models.Topic]) -> models.Topic:
    import models

    key = (section.id, item["topic"])
    if key in cache:
        return cache[key]
    topic = (
        db.query(models.Topic)
        .filter(models.Topic.course_id == course.id)
        .filter(models.Topic.section_id == section.id)
        .filter(models.Topic.title == item["topic"])
        .first()
    )
    if topic is None:
        topic = models.Topic(
            course_id=course.id,
            section_id=section.id,
            title=item["topic"],
            theory_content=f"Тема соответствует номеру {item['task_number']} экзамена. Условие показывается как изображение из банка заданий.",
            examples="Разберите изображение задания, выполните решение по таймеру и отправьте ответ или файл решения.",
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
    cache[key] = topic
    return topic


def _extract_task_images(
    pdf_path: Path,
    exam: str,
    output_dir: Path,
    context_dir: Path,
    answers: dict[str, str],
    max_per_number: int,
    dpi: int,
    poppler_path: str | None,
) -> list[dict]:
    config = EXAM_CONFIG[exam]
    selected: list[dict] = []
    per_number: dict[int, int] = defaultdict(int)
    seen_task_keys: set[tuple[int, str]] = set()
    answer_start_page = _find_answer_start_page(pdf_path)

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            if answer_start_page is not None and page_index >= answer_start_page:
                break
            markers = _markers_for_page(page, page_index)
            markers = [marker for marker in markers if marker.task_number in config["numbers"]]
            if not markers:
                continue
            page_image = None
            page_context_path = _context_image_for_page(
                pdf_path=pdf_path,
                page=page,
                page_index=page_index,
                markers=markers,
                output_dir=context_dir,
                dpi=dpi,
                poppler_path=poppler_path,
            )
            for index, marker in enumerate(markers):
                marker_key = (marker.task_number, marker.analog_number)
                if marker_key in seen_task_keys:
                    continue
                if per_number[marker.task_number] >= max_per_number:
                    continue
                next_top = markers[index + 1].top if index + 1 < len(markers) else min(page.height - 36, marker.top + 260)
                if next_top <= marker.top + 24:
                    next_top = min(page.height - 36, marker.top + 220)
                if page_image is None:
                    page_image = _render_page(pdf_path, page_index, dpi, poppler_path)
                seen_task_keys.add(marker_key)
                image_rel_path = _crop_task_image(
                    image=page_image,
                    page=page,
                    marker=marker,
                    next_top=next_top,
                    output_dir=output_dir,
                    exam=exam,
                    dpi=dpi,
                )
                per_number[marker.task_number] += 1
                selected.append(
                    _task_manifest_item(
                        exam=exam,
                        pdf_path=pdf_path,
                        page=page,
                        marker=marker,
                        image_path=image_rel_path,
                        context_image_path=page_context_path,
                        answer=answers.get(_answer_key(marker.task_number, marker.analog_number), ""),
                    )
                )
            if all(per_number[number] >= max_per_number for number in config["numbers"]):
                break
    return selected


def _markers_for_page(page, page_index: int) -> list[Marker]:
    words = page.extract_words(x_tolerance=2, y_tolerance=4, keep_blank_chars=False) or []
    markers: list[Marker] = []
    for index, word in enumerate(words[:-1]):
        if not word["text"].lower().startswith("задача"):
            continue
        number_word = words[index + 1]["text"].strip().rstrip(".")
        match = re.match(r"(\d+)[\.,](\d+(?:\.\d+)*)", number_word)
        if not match:
            continue
        text = f"{word['text']} {number_word}"
        markers.append(
            Marker(
                task_number=int(match.group(1)),
                analog_number=match.group(2),
                page_index=page_index,
                top=max(0, min(word["top"], words[index + 1]["top"]) - 8),
                bottom=max(word["bottom"], words[index + 1]["bottom"]),
                text=text,
            )
        )
    return markers


def _task_manifest_item(
    exam: str,
    pdf_path: Path,
    page,
    marker: Marker,
    image_path: str,
    context_image_path: str | None,
    answer: str,
) -> dict:
    section_title, topic, part, max_score = EXAM_CONFIG[exam]["numbers"][marker.task_number]
    answer_format = "краткий ответ" if part == 1 else "развёрнутое решение"
    difficulty = "базовый" if part == 1 else "сложный"
    title = f"Задание {marker.task_number}.{marker.analog_number}"
    return {
        "exam": exam,
        "part": part,
        "task_number": marker.task_number,
        "prototype_number": str(marker.task_number),
        "analog_number": marker.analog_number,
        "title": title,
        "section_title": section_title,
        "topic": topic,
        "difficulty": difficulty,
        "max_score": max_score,
        "task_type": topic.lower(),
        "answer_format": answer_format,
        "condition_text": f"{title}. Условие задания отображается изображением из PDF-банка.",
        "image_path": image_path,
        "context_image_path": context_image_path,
        "answer": answer,
        "solution": "",
        "criteria": _criteria_for(part, max_score),
        "source_file": pdf_path.name,
        "source_page": marker.page_index + 1,
        "is_active": True,
    }


def _criteria_for(part: int, max_score: int) -> str:
    if part == 1:
        return "Краткий ответ проверяется по эталону из банка заданий. Решение ученика не показывается до отправки попытки."
    return f"Развёрнутое решение оценивается преподавателем по критериям второй части. Максимум: {max_score} балла."


def _crop_task_image(image: Image.Image, page, marker: Marker, next_top: float, output_dir: Path, exam: str, dpi: int) -> str:
    scale = dpi / 72
    left = int(24 * scale)
    top = int(max(marker.top - 8, 0) * scale)
    right = int((page.width - 24) * scale)
    bottom = int(min(next_top + 8, page.height - 30) * scale)
    crop = image.crop((left, top, right, bottom))
    file_name = f"{exam.lower()}_{marker.task_number:02d}_{_safe_name(marker.analog_number)}_p{marker.page_index + 1}.png"
    target = output_dir / file_name
    crop.save(target, "PNG", optimize=True)
    return _relative_static_path(target)


def _context_image_for_page(
    pdf_path: Path,
    page,
    page_index: int,
    markers: list[Marker],
    output_dir: Path,
    dpi: int,
    poppler_path: str | None,
) -> str | None:
    first_top = min(marker.top for marker in markers)
    text_before = (page.crop((0, 0, page.width, first_top)).extract_text() or "").lower()
    if "текст к задач" not in text_before and "рис." not in text_before and "на плане" not in text_before:
        return None
    image = _render_page(pdf_path, page_index, dpi, poppler_path)
    scale = dpi / 72
    crop = image.crop((int(24 * scale), int(70 * scale), int((page.width - 24) * scale), int(max(first_top - 4, 100) * scale)))
    target = output_dir / f"context_p{page_index + 1}.png"
    crop.save(target, "PNG", optimize=True)
    return _relative_static_path(target)


def _render_page(pdf_path: Path, page_index: int, dpi: int, poppler_path: str | None) -> Image.Image:
    images = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        first_page=page_index + 1,
        last_page=page_index + 1,
        fmt="png",
        poppler_path=poppler_path,
        thread_count=1,
    )
    return images[0]


def _extract_answers(pdf_path: Path) -> dict[str, str]:
    answers: dict[str, str] = {}
    start_page = _find_answer_start_page(pdf_path)
    if start_page is None:
        return answers
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages[start_page:]:
            text = page.extract_text() or ""
            for line in text.splitlines():
                for match in ANSWER_LINE_RE.finditer(line):
                    answer = match.group(3).strip()
                    answer = re.split(r"\s+№\s*\d", answer, maxsplit=1)[0].strip()
                    if answer:
                        answers[_answer_key(int(match.group(1)), match.group(2))] = answer.rstrip(".")
    return answers


def _find_answer_start_page(pdf_path: Path) -> int | None:
    with pdfplumber.open(str(pdf_path)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines()[:8]]
            if any(line == "ОТВЕТЫ" for line in lines):
                return index
    return None


def _answer_key(task_number: int, analog_number: str) -> str:
    return f"{task_number}.{analog_number}"


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_-]+", "_", value)


def _relative_static_path(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def _default_poppler_path() -> str | None:
    env_path = os.getenv("POPPLER_PATH")
    candidates = [Path(env_path)] if env_path else []
    for candidate in candidates:
        if (candidate / "pdftoppm.exe").exists() or (candidate / "pdftoppm").exists():
            return str(candidate)
    return None


def _now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


if __name__ == "__main__":
    raise SystemExit(main())
