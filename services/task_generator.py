from __future__ import annotations

from services.ai_client import AIClient, AIClientFactory
from services.math_tasks import build_math_task


class TaskGeneratorAgent:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("task_generator")

    def generate_similar(self, task, count: int = 5) -> list[dict]:
        fallback_tasks = []
        topic_index = _topic_index(task)
        section_number = task.section.number if task.section else 1
        for index in range(1, count + 1):
            content = build_math_task(
                task.course.exam_type if task.course else "ОГЭ",
                section_number,
                task.section.title if task.section else task.title,
                task.topic.title if task.topic else task.title,
                topic_index=topic_index,
                variant=index + 2,
                shift=(task.id % 5) + index,
            )
            fallback_tasks.append(
                {
                    "title": f"Похожее задание {index}",
                    "condition_text": content["condition_text"],
                    "correct_answer": content["correct_answer"],
                    "short_solution": content["solution_explanation"],
                    "topic": task.topic.title if task.topic else "",
                    "difficulty": content["difficulty"],
                    "quality_focus": "полнота, логика, оформление, устойчивость навыка",
                    "skill_stability_estimate": max(45, 90 - index * 5),
                }
            )

        llm_text = self.ai_client.generate_similar_task(
            task,
            topic=task.topic,
            difficulty=task.difficulty,
            fallback="",
        )
        if not llm_text:
            return fallback_tasks
        # The local structured fallback is kept for API stability; LLM text is added as a note.
        fallback_tasks[0]["llm_note"] = llm_text[:700]
        return fallback_tasks


def _topic_index(task) -> int:
    try:
        topics = sorted(task.section.topics, key=lambda item: item.id)
    except Exception:
        return 1
    return next((index for index, topic in enumerate(topics, start=1) if topic.id == task.topic_id), 1)
