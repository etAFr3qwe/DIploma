from __future__ import annotations

import warnings
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, mean_squared_error, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

import models
from data.sample_data import seed_sample_data
from database import SessionLocal, ensure_database_schema


def train_model(db: Session, force: bool = True) -> dict:
    """Train a lightweight MLP classifier on current task attempts."""
    attempts = db.query(models.Attempt).filter(models.Attempt.is_correct.isnot(None)).all()
    if len(attempts) < 8 or len({attempt.is_correct for attempt in attempts}) < 2:
        return {
            "samples": len(attempts),
            "input_size": 0,
            "train_loss": 0.0,
            "test_loss": 0.0,
            "accuracy": 0.0,
            "roc_auc": None,
            "message": "Недостаточно разнообразных попыток для обучения рекомендательной модели.",
        }

    x = np.array([_features(attempt) for attempt in attempts], dtype=float)
    y = np.array([1 if attempt.is_correct else 0 for attempt in attempts], dtype=int)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.3, random_state=42, stratify=y)

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_test = scaler.transform(x_test)

    model = MLPClassifier(hidden_layer_sizes=(24, 12), max_iter=500, random_state=42)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        model.fit(x_train, y_train)
    scores = model.predict_proba(x_test)[:, 1]
    predictions = (scores >= 0.5).astype(int)

    try:
        auc = float(roc_auc_score(y_test, scores))
    except ValueError:
        auc = None

    return {
        "samples": len(attempts),
        "input_size": x.shape[1],
        "train_loss": round(float(getattr(model, "loss_", 0.0)), 4),
        "test_loss": round(float(mean_squared_error(y_test, scores)), 4),
        "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
        "roc_auc": round(auc, 4) if auc is not None else None,
        "message": "Рекомендательная модель заданий обучена на истории попыток.",
    }


def _features(attempt: models.Attempt) -> list[float]:
    task = attempt.task
    return [
        task.section.number if task.section else 0,
        task.max_score or 1,
        1 if task.difficulty == "повышенный" else 0,
        attempt.attempt_number or 1,
        min(attempt.duration_seconds or 0, 2400) / 2400,
        1 if attempt.score and attempt.score > 0 else 0,
    ]


def main() -> None:
    ensure_database_schema()
    db = SessionLocal()
    try:
        seed_sample_data(db)
        print(train_model(db, force=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
