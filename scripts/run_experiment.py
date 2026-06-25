from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import mean_absolute_error, ndcg_score, precision_score, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import StandardScaler


@dataclass
class SyntheticData:
    features: np.ndarray
    labels: np.ndarray
    exam_scores: np.ndarray
    student_ids: np.ndarray
    task_ids: np.ndarray


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-value))


def generate_irt_data(students: int = 180, tasks: int = 90, random_state: int = 42) -> SyntheticData:
    rng = np.random.default_rng(random_state)
    ability = rng.normal(0, 1, size=students)
    diligence = rng.uniform(0.45, 1.0, size=students)
    task_difficulty = rng.normal(0, 1, size=tasks)
    task_topic = rng.integers(0, 12, size=tasks)

    rows = []
    labels = []
    student_ids = []
    task_ids = []
    topic_success = np.zeros((students, 12), dtype=float)
    topic_count = np.zeros((students, 12), dtype=float)

    for student_id in range(students):
        sampled_tasks = rng.choice(tasks, size=42, replace=False)
        for task_id in sampled_tasks:
            topic = task_topic[task_id]
            prior_success = topic_success[student_id, topic] / max(1.0, topic_count[student_id, topic])
            attempts_penalty = rng.integers(1, 4)
            time_factor = rng.normal(0.0, 0.25)
            probability = sigmoid(
                ability[student_id]
                + 0.8 * diligence[student_id]
                + 0.45 * prior_success
                - task_difficulty[task_id]
                - 0.18 * (attempts_penalty - 1)
                - 0.12 * time_factor
            )
            correct = int(rng.random() < probability)
            topic_success[student_id, topic] += correct
            topic_count[student_id, topic] += 1
            rows.append(
                [
                    ability[student_id],
                    diligence[student_id],
                    task_difficulty[task_id],
                    topic / 12,
                    prior_success,
                    attempts_penalty,
                    time_factor,
                ]
            )
            labels.append(correct)
            student_ids.append(student_id)
            task_ids.append(task_id)

    final_topic_success = topic_success / np.maximum(topic_count, 1)
    coverage = (topic_count > 0).mean(axis=1)
    exam_scores = 100 * (0.45 * sigmoid(ability) + 0.25 * final_topic_success.mean(axis=1) + 0.20 * coverage + 0.10 * diligence)
    row_scores = np.array([exam_scores[student_id] for student_id in student_ids])

    return SyntheticData(
        features=np.array(rows, dtype=float),
        labels=np.array(labels, dtype=int),
        exam_scores=row_scores,
        student_ids=np.array(student_ids, dtype=int),
        task_ids=np.array(task_ids, dtype=int),
    )


def precision_at_10(y_true: np.ndarray, y_score: np.ndarray) -> float:
    order = np.argsort(y_score)[::-1][:10]
    return float(y_true[order].mean()) if len(order) else 0.0


def run_experiment(random_state: int = 42) -> dict[str, float]:
    data = generate_irt_data(random_state=random_state)
    x_train, x_test, y_train, y_test, score_train, score_test = train_test_split(
        data.features,
        data.labels,
        data.exam_scores,
        test_size=0.3,
        random_state=random_state,
        stratify=data.labels,
    )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)

    recommender = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=random_state)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        recommender.fit(x_train_scaled, y_train)
    probabilities = recommender.predict_proba(x_test_scaled)[:, 1]

    forecast_model = MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=700, random_state=random_state)
    forecast_model.fit(x_train_scaled, score_train)
    predicted_scores = forecast_model.predict(x_test_scaled)

    baseline_probability = np.full_like(probabilities, fill_value=float(y_train.mean()))
    baseline_score = np.full_like(score_test, fill_value=float(score_train.mean()))

    metrics = {
        "AUC модели": roc_auc_score(y_test, probabilities),
        "AUC baseline": roc_auc_score(y_test, baseline_probability),
        "precision@10 модели": precision_at_10(y_test, probabilities),
        "precision@10 baseline": precision_at_10(y_test, baseline_probability),
        "NDCG@10 модели": ndcg_score([y_test], [probabilities], k=10),
        "NDCG@10 baseline": ndcg_score([y_test], [baseline_probability], k=10),
        "MAE прогноза": mean_absolute_error(score_test, predicted_scores),
        "MAE baseline": mean_absolute_error(score_test, baseline_score),
        "R2 прогноза": r2_score(score_test, predicted_scores),
        "R2 baseline": r2_score(score_test, baseline_score),
        "точность классификации": precision_score(y_test, probabilities >= 0.5, zero_division=0),
    }
    return {key: round(float(value), 4) for key, value in metrics.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Экспериментальная оценка рекомендательной и прогнозной модели.")
    parser.add_argument("--seed", type=int, default=42, help="Начальное значение генератора случайных чисел.")
    args = parser.parse_args()
    metrics = run_experiment(args.seed)
    print("Экспериментальная оценка на синтетических IRT-данных")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
