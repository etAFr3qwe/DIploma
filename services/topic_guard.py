from __future__ import annotations

from services.ai_client import AIClient, AIClientFactory


FORBIDDEN = [
    "списать",
    "шпаргал",
    "скажи ответ",
    "дай ответ",
    "без решения",
    "сочинение",
    "реферат",
    "обойти проверку",
]

MATH_KEYWORDS = [
    "математ",
    "огэ",
    "егэ",
    "уравнен",
    "неравен",
    "функц",
    "график",
    "производн",
    "геометр",
    "вероят",
    "параметр",
    "тригоном",
    "задач",
    "балл",
    "решен",
    "дроб",
    "процент",
]


class TopicGuardAgent:
    def __init__(self, ai_client: AIClient | None = None) -> None:
        self.ai_client = ai_client or AIClientFactory.create_for_agent("topic_guard")

    def classify(self, message: str) -> dict:
        text = message.lower()
        if any(keyword in text for keyword in FORBIDDEN):
            fallback = {
                "allowed": False,
                "reason": "Запрос не помогает честной подготовке. Я могу объяснить метод, разобрать ошибку или предложить похожую тренировку.",
                "detected_topic": "академическая честность",
            }
            return self.ai_client.cheap_classify(message, fallback)

        detected = self._detect_topic(text)
        allowed = bool(detected)
        fallback = {
            "allowed": allowed,
            "reason": (
                "Запрос относится к подготовке по математике."
                if allowed
                else "Вернёмся к математике ОГЭ/ЕГЭ и текущему заданию."
            ),
            "detected_topic": detected or "вне темы",
        }
        return self.ai_client.cheap_classify(message, fallback)

    @staticmethod
    def _detect_topic(text: str) -> str:
        if "производ" in text:
            return "производная"
        if "параметр" in text:
            return "параметры"
        if "тригоном" in text or "синус" in text or "косинус" in text:
            return "тригонометрия"
        if "геометр" in text or "треуг" in text or "окруж" in text:
            return "геометрия"
        if "вероят" in text:
            return "вероятность"
        if "урав" in text or "алгеб" in text:
            return "алгебра"
        if any(keyword in text for keyword in MATH_KEYWORDS):
            return "математика"
        return ""
