from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import models
from database import SessionLocal


EXPECTED_BY_EXAM_NUMBER = {
    "OGE": {
        **{number: (1, "Практико-ориентированные задачи") for number in range(1, 6)},
        6: (1, "Числа и вычисления"),
        7: (1, "Координатная прямая"),
        8: (1, "Степени и корни"),
        9: (1, "Уравнения"),
        10: (1, "Вероятность"),
        11: (1, "Графики функций"),
        12: (1, "Функции"),
        13: (1, "Неравенства"),
        14: (1, "Последовательности и прогрессии"),
        15: (1, "Геометрия"),
        16: (1, "Геометрия"),
        17: (1, "Геометрия"),
        18: (1, "Геометрия"),
        19: (1, "Геометрия и анализ утверждений"),
        20: (2, "Выражения, уравнения и неравенства"),
        21: (2, "Текстовые задачи"),
        22: (2, "Построение графиков функций"),
        23: (2, "Геометрические задачи на вычисление"),
        24: (2, "Геометрические задачи на доказательство"),
        25: (2, "Геометрические задачи повышенной сложности"),
    },
    "EGE_PROFILE": {
        1: (1, "Планиметрия"),
        2: (1, "Векторы"),
        3: (1, "Стереометрия"),
        4: (1, "Вероятность"),
        5: (1, "Вероятность"),
        6: (1, "Уравнения"),
        7: (1, "Вычисления и преобразования"),
        8: (1, "Производная и исследование функций"),
        9: (1, "Прикладные задачи"),
        10: (1, "Текстовые задачи"),
        11: (1, "Графики и функции"),
        12: (1, "Экстремумы"),
        13: (2, "Уравнения"),
        14: (2, "Стереометрия"),
        15: (2, "Неравенства"),
        16: (2, "Финансовая математика"),
        17: (2, "Планиметрия"),
        18: (2, "Задачи с параметром"),
        19: (2, "Нестандартные задачи"),
    },
}


RULES = [
    {
        "label": "тригонометрия",
        "topic_markers": ["тригоном", "отбор корней"],
        "required": ["sin", "cos", "tg", "ctg", "pi", "π", "радиан", "угол"],
        "reason": "в тригонометрической теме должны быть sin/cos/tg/ctg, pi, угол или отбор корней",
    },
    {
        "label": "показательные уравнения",
        "topic_markers": ["показательн"],
        "required": ["^", "степен", "2^", "3^", "5^"],
        "reason": "в показательной теме должны быть степени с переменной или переход к общему основанию",
    },
    {
        "label": "логарифмы",
        "topic_markers": ["логарифм", "log", "ln"],
        "required": ["log", "ln", "логарифм", "одз"],
        "reason": "в логарифмической теме должны быть log/ln, логарифм или ОДЗ",
    },
    {
        "label": "производная",
        "topic_markers": ["производ", "монотон", "экстрем"],
        "required": ["производ", "f'", "y'", "s'", "касательн", "монотон", "экстрем", "наибольш", "наименьш"],
        "reason": "в теме производной должны быть производная, касательная, монотонность или экстремум",
    },
    {
        "label": "вероятность",
        "topic_markers": ["вероят", "событ", "комбинатор", "независим"],
        "required": ["вероят", "случайно", "выбира", "монет", "шар", "исход", "событ"],
        "reason": "в вероятностной теме должны быть случайный выбор, исходы или вероятность",
    },
    {
        "label": "геометрия",
        "topic_markers": ["геометр", "треуг", "окруж", "площад", "трапец", "параллелограмм", "призм", "пирам", "углы", "хорды"],
        "required": ["треуг", "окруж", "площад", "угол", "углы", "радиус", "сторон", "хорд", "катет", "гипотенуз", "призм", "пирам", "основан", "высот"],
        "reason": "в геометрической теме должны быть фигуры, углы, стороны, площади или пространственные тела",
    },
]


FORBIDDEN = [
    {
        "topic_markers": ["тригоном", "отбор корней"],
        "forbidden": ["3^(x+1)", "log", "логарифм"],
        "reason": "тригонометрическая тема содержит показательную или логарифмическую формулировку",
    },
    {
        "topic_markers": ["геометр", "треуг", "окруж", "площад", "трапец", "призм", "пирам"],
        "forbidden": ["log", "sin x", "cos x", "производн", "кредит", "вклад"],
        "reason": "геометрическая тема содержит признаки другой области",
    },
    {
        "topic_markers": ["вероят"],
        "forbidden": ["производн", "log", "sin", "cos", "площадь трапеции"],
        "reason": "тема вероятности содержит признаки другой области",
    },
]


def main() -> int:
    db = SessionLocal()
    try:
        problems = []
        tasks = db.query(models.Task).join(models.Topic).join(models.ExamSection).join(models.Course).all()
        for task in tasks:
            if task.image_path:
                problems.extend(_validate_imported_task(task))
                continue
            topic_name = task.topic.title.lower() if task.topic else ""
            haystack = " ".join(
                [
                    task.title or "",
                    task.condition_text or "",
                    task.solution_explanation or "",
                    task.criteria or "",
                    task.task_type or "",
                ]
            ).lower()
            topic_text = " ".join(
                [
                    task.topic.title if task.topic else "",
                    task.section.title if task.section else "",
                    task.course.title if task.course else "",
                ]
            ).lower()

            for rule in RULES:
                if rule["label"] == "геометрия" and "прогресс" in topic_name:
                    continue
                if rule["label"] == "вероятность" and not _contains_any(topic_name, rule["topic_markers"]):
                    continue
                if _contains_any(topic_text, rule["topic_markers"]) and not _contains_any(haystack, rule["required"]):
                    problems.append(_problem(task, rule["reason"]))

            for rule in FORBIDDEN:
                if _contains_any(topic_text, rule["topic_markers"]) and _contains_any(haystack, rule["forbidden"]):
                    problems.append(_problem(task, rule["reason"]))

        if problems:
            for item in problems:
                print(f"ID: {item['id']}")
                print(f"Курс: {item['course']}")
                print(f"Тема: {item['topic']}")
                print(f"Условие: {item['condition']}")
                print(f"Причина: {item['reason']}")
                print("-" * 80)
            return 1

        print(f"Проверено заданий: {len(tasks)}. Очевидных несоответствий темы и условия не найдено.")
        return 0
    finally:
        db.close()


def _contains_any(text: str, markers: list[str]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _problem(task: models.Task, reason: str) -> dict[str, str | int]:
    return {
        "id": task.id,
        "course": task.course.title if task.course else "-",
        "topic": task.topic.title if task.topic else "-",
        "condition": task.condition_text,
        "reason": reason,
    }


def _validate_imported_task(task: models.Task) -> list[dict[str, str | int]]:
    expected = EXPECTED_BY_EXAM_NUMBER.get(task.exam_type, {}).get(task.task_number)
    if expected is None:
        return [_problem(task, "для импортированного задания не найдено ожидаемое соответствие номера экзамена")]
    expected_part, expected_topic = expected
    problems = []
    if task.part != expected_part:
        problems.append(_problem(task, f"ожидалась часть {expected_part}, но в базе указана часть {task.part}"))
    actual_topic = task.bank_topic or (task.topic.title if task.topic else "")
    if actual_topic != expected_topic:
        problems.append(_problem(task, f"ожидалась тема «{expected_topic}», но указана «{actual_topic}»"))
    if not task.image_path:
        problems.append(_problem(task, "у импортированного задания отсутствует изображение условия"))
    if task.part == 2 and task.answer_format != "развёрнутое решение":
        problems.append(_problem(task, "для второй части должен быть формат «развёрнутое решение»"))
    if task.part == 1 and task.answer_format != "краткий ответ":
        problems.append(_problem(task, "для первой части должен быть формат «краткий ответ»"))
    return problems


if __name__ == "__main__":
    sys.exit(main())
