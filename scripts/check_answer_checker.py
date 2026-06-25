from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.answer_checker import compare_answers


CASES = [
    ("1/2", "0.5", True),
    ("0,5", "1/2", True),
    ("sqrt(4)", "2", True),
    ("pi", "3.1415926", True),
    ("2*x + 2*x", "4*x", True),
]


def main() -> None:
    for student, correct, expected in CASES:
        result = compare_answers(student, correct)
        verdict = "OK" if result.is_correct is expected else "FAIL"
        print(f"{verdict}: {student!r} и {correct!r} -> {result.is_correct}; {result.message}")


if __name__ == "__main__":
    main()
