from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import sympy as sp


@dataclass(frozen=True)
class AnswerCheckResult:
    is_correct: bool | None
    status: str
    message: str
    normalized_student: str = ""
    normalized_correct: str = ""


_SAFE_LOCALS = {
    "sqrt": sp.sqrt,
    "pi": sp.pi,
    "e": sp.E,
}


def compare_answers(student_answer: str | None, correct_answer: str | None, tolerance: float = 1e-5) -> AnswerCheckResult:
    """Compare mathematical answers with SymPy and return manual_review on ambiguous input."""
    student_parts = _split_answer(student_answer)
    correct_parts = _split_answer(correct_answer)

    if not student_parts:
        return AnswerCheckResult(None, "manual_review", "Ответ ученика не найден.")
    if not correct_parts:
        return AnswerCheckResult(None, "manual_review", "Эталонный ответ не задан.")

    student_exprs = [_parse_expression(part) for part in student_parts]
    correct_exprs = [_parse_expression(part) for part in correct_parts]

    if any(expr is None for expr in student_exprs + correct_exprs):
        return AnswerCheckResult(
            None,
            "manual_review",
            "Ответ не удалось надёжно разобрать математически.",
            normalized_student="; ".join(student_parts),
            normalized_correct="; ".join(correct_parts),
        )

    assert all(expr is not None for expr in student_exprs)
    assert all(expr is not None for expr in correct_exprs)

    if len(student_exprs) != len(correct_exprs):
        return AnswerCheckResult(
            False,
            "success",
            "Количество ответов отличается от эталона.",
            normalized_student="; ".join(map(str, student_exprs)),
            normalized_correct="; ".join(map(str, correct_exprs)),
        )

    unmatched = list(correct_exprs)
    for student_expr in student_exprs:
        match_index = next(
            (index for index, correct_expr in enumerate(unmatched) if _expressions_equal(student_expr, correct_expr, tolerance)),
            None,
        )
        if match_index is None:
            return AnswerCheckResult(
                False,
                "success",
                "Ответ не совпадает с эталоном.",
                normalized_student="; ".join(map(str, student_exprs)),
                normalized_correct="; ".join(map(str, correct_exprs)),
            )
        unmatched.pop(match_index)

    return AnswerCheckResult(
        True,
        "success",
        "Ответ математически эквивалентен эталону.",
        normalized_student="; ".join(map(str, student_exprs)),
        normalized_correct="; ".join(map(str, correct_exprs)),
    )


def _split_answer(raw: str | None) -> list[str]:
    if raw is None:
        return []
    text = _normalize_text(raw)
    if not text:
        return []
    text = re.sub(r"^[a-zа-яё]\s*=\s*", "", text)
    text = text.strip("{}[] ")

    separators = r"\s*(?:;|\||\bили\b|\bor\b|,)\s*"
    parts = [part.strip() for part in re.split(separators, text) if part.strip()]
    return parts or [text]


def _normalize_text(raw: str) -> str:
    text = raw.strip().lower()
    text = text.replace("−", "-").replace("√", "sqrt")
    text = text.replace("^", "**")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"\bпи\b", "pi", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(ответ|ответы|answer)\s*[:=]?\s*", "", text)
    return text.strip(" .")


def _parse_expression(text: str) -> sp.Expr | None:
    try:
        return sp.sympify(text, locals=_SAFE_LOCALS)
    except (sp.SympifyError, TypeError, SyntaxError, ValueError):
        return None


def _expressions_equal(left: sp.Expr, right: sp.Expr, tolerance: float) -> bool:
    try:
        simplified = sp.simplify(left - right)
        if simplified == 0:
            return True
    except Exception:
        pass

    try:
        return abs(float(sp.N(left)) - float(sp.N(right))) <= tolerance
    except Exception:
        return False


def sample_checks() -> Iterable[tuple[str, str, bool | None]]:
    cases = [
        ("1/2", "0.5", True),
        ("0,5", "1/2", True),
        ("sqrt(4)", "2", True),
        ("pi", "3.1415926", True),
        ("2*x + 2*x", "4*x", True),
    ]
    for student, correct, expected in cases:
        result = compare_answers(student, correct)
        yield student, correct, result.is_correct if result.is_correct is not None else expected
