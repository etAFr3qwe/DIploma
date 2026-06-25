from __future__ import annotations

import numpy as np
import torch
from torch import nn

import models


class TaskRelevanceNet(nn.Module):
    """Small PyTorch network for predicting relevance of an exam task."""

    def __init__(self, input_size: int = 9) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.layers(features).squeeze(-1)


def build_task_features(user: models.User, task: models.Task, attempts: list[models.Attempt]) -> np.ndarray:
    topic_attempts = [attempt for attempt in attempts if attempt.task.topic_id == task.topic_id and attempt.is_correct is not None]
    section_attempts = [attempt for attempt in attempts if attempt.task.section_id == task.section_id and attempt.is_correct is not None]
    all_checked = [attempt for attempt in attempts if attempt.is_correct is not None]
    topic_success = _success_rate(topic_attempts)
    section_success = _success_rate(section_attempts)
    overall_success = _success_rate(all_checked)
    task_attempts = [attempt for attempt in attempts if attempt.task_id == task.id]
    average_time = (
        sum((attempt.duration_seconds or 0) for attempt in task_attempts) / len(task_attempts)
        if task_attempts
        else 600
    )
    return np.array(
        [
            1 if user.target_exam == task.course.exam_type else 0,
            task.section.number / 20,
            task.max_score / 3,
            1 if task.difficulty == "повышенный" else 0,
            topic_success,
            section_success,
            overall_success,
            len(task_attempts) / 5,
            min(average_time, 2400) / 2400,
        ],
        dtype=np.float32,
    )


def build_training_dataset(user: models.User, tasks: list[models.Task], attempts: list[models.Attempt]) -> tuple[torch.Tensor, torch.Tensor]:
    labels_by_task = {
        attempt.task_id: 1.0 if attempt.is_correct else 0.0
        for attempt in attempts
        if attempt.is_correct is not None
    }
    features = [build_task_features(user, task, attempts) for task in tasks]
    labels = [labels_by_task.get(task.id, 0.0) for task in tasks]
    return torch.tensor(np.array(features), dtype=torch.float32), torch.tensor(np.array(labels), dtype=torch.float32)


def _success_rate(attempts: list[models.Attempt]) -> float:
    if not attempts:
        return 0.5
    return sum(1 for attempt in attempts if attempt.is_correct) / len(attempts)
