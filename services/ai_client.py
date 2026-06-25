from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


if load_dotenv:
    load_dotenv()


logger = logging.getLogger(__name__)


AGENT_SETTINGS: dict[str, dict[str, str]] = {
    "topic_guard": {
        "label": "TopicGuardAgent",
        "env_prefix": "TOPIC_GUARD",
        "default_provider": "deepseek",
        "default_model": "deepseek-chat",
    },
    "tutor_chat": {
        "label": "TutorChatAgent",
        "env_prefix": "TUTOR_CHAT",
        "default_provider": "openai",
        "default_model": "gpt-4o-mini",
    },
    "text_recognition": {
        "label": "TextRecognitionAgent",
        "env_prefix": "TEXT_RECOGNITION",
        "default_provider": "yandex_ocr",
        "default_model": "page",
    },
    "solution_review": {
        "label": "SolutionReviewAgent",
        "env_prefix": "SOLUTION_REVIEW",
        "default_provider": "openai",
        "default_model": "gpt-4o",
    },
    "task_generator": {
        "label": "TaskGeneratorAgent",
        "env_prefix": "TASK_GENERATOR",
        "default_provider": "deepseek",
        "default_model": "deepseek-chat",
    },
}

AGENT_ALIASES = {
    "topicguard": "topic_guard",
    "topic_guard_agent": "topic_guard",
    "tutoring": "tutor_chat",
    "tutor": "tutor_chat",
    "tutor_chat_agent": "tutor_chat",
    "ocr": "text_recognition",
    "text_recognition_agent": "text_recognition",
    "solution": "solution_review",
    "solution_review_agent": "solution_review",
    "generator": "task_generator",
    "task_generator_agent": "task_generator",
}

PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "anthropic": "https://api.anthropic.com/v1",
    "yandex_gpt": "https://ai.api.cloud.yandex.net/v1",
    "yandex_ocr": "https://ai.api.cloud.yandex.net/ocr/v1/recognizeText",
    "mock": "",
}

PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "yandex_gpt": "YANDEX_GPT_API_KEY",
    "yandex_ocr": "YANDEX_API_KEY",
    "mock": "",
}

PROVIDER_BASE_ENV = {
    "openai": "OPENAI_BASE_URL",
    "deepseek": "DEEPSEEK_BASE_URL",
    "gemini": "GEMINI_BASE_URL",
    "anthropic": "ANTHROPIC_BASE_URL",
    "yandex_gpt": "YANDEX_GPT_BASE_URL",
    "yandex_ocr": "YANDEX_OCR_BASE_URL",
    "mock": "",
}


@dataclass(frozen=True)
class AIProviderConfig:
    agent_key: str
    agent_label: str
    env_prefix: str
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout: float
    mock_mode: bool
    unsupported_provider: str | None = None


class AIProvider:
    """Базовый интерфейс провайдера внешней ИИ-модели."""

    name = "base"
    supports_vision = False

    def __init__(self, config: AIProviderConfig) -> None:
        self.config = config
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(not self.config.mock_mode and self.config.api_key and self.config.model and httpx)

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        raise NotImplementedError

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        self._remember_error(f"Провайдер для {self.config.agent_label} не поддерживает изображения.")
        return fallback

    def vision_review_many(self, system_prompt: str, user_prompt: str, file_paths: list[str], fallback: str) -> str:
        paths = [path for path in file_paths if path]
        if not paths:
            return fallback
        if len(paths) == 1:
            return self.vision_review(system_prompt, user_prompt, paths[0], fallback)

        page_results: list[str] = []
        for index, path in enumerate(paths, start=1):
            page_prompt = (
                f"{user_prompt}\n\n"
                f"Это страница {index} из {len(paths)} одного решения одной попытки. "
                "Не оценивай её как отдельное решение задания."
            )
            page_result = self.vision_review(system_prompt, page_prompt, path, "")
            if page_result.strip():
                page_results.append(f"Страница {index}: {page_result.strip()}")
        return "\n".join(page_results) or fallback

    def health_status(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "mock",
                "api_connected": False,
                "mock_mode": True,
                "message": "AI_MOCK_MODE включен, реальные API не используются.",
            }
        if self.config.unsupported_provider:
            return {
                "provider": self.config.unsupported_provider,
                "model": self.config.model,
                "status": "error",
                "api_connected": False,
                "mock_mode": False,
                "message": f"Провайдер {self.config.unsupported_provider} не поддерживается.",
            }
        if not self.config.api_key:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "fallback",
                "api_connected": False,
                "mock_mode": False,
                "message": f"Не найден API-ключ для {self.config.agent_label}.",
            }
        if not self.config.model:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "error",
                "api_connected": False,
                "mock_mode": False,
                "message": f"Модель для {self.config.agent_label} не указана.",
            }
        if httpx is None:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "error",
                "api_connected": False,
                "mock_mode": False,
                "message": "Библиотека httpx недоступна.",
            }
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "status": "ok" if not self.last_error else "warning",
            "api_connected": True,
            "mock_mode": False,
            "message": self.last_error or "Конфигурация API заполнена.",
        }

    def _unavailable(self, fallback: str) -> str:
        if self.config.mock_mode:
            self._remember_error("AI_MOCK_MODE включен, реальные API не используются.")
        elif self.config.unsupported_provider:
            self._remember_error(f"Провайдер {self.config.unsupported_provider} не поддерживается.")
        elif not self.config.api_key:
            self._remember_error(f"Не найден API-ключ для {self.config.agent_label}.")
        elif not self.config.model:
            self._remember_error(f"Модель для {self.config.agent_label} не указана.")
        elif httpx is None:
            self._remember_error("Библиотека httpx недоступна, используется локальный тестовый ответ.")
        return fallback

    def _remember_error(self, message: str) -> None:
        self.last_error = message
        logger.warning(message)


class OpenAIProvider(AIProvider):
    name = "openai"
    supports_vision = True

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return self._post_chat_completion(payload, fallback)

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        image_payload = _image_data_url(file_path)
        if image_payload is None:
            self._remember_error(f"Провайдер для {self.config.agent_label} не поддерживает распознавание этого типа файла.")
            return fallback
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": image_payload}},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 1200,
        }
        return self._post_chat_completion(payload, fallback)

    def vision_review_many(self, system_prompt: str, user_prompt: str, file_paths: list[str], fallback: str) -> str:
        if not self.enabled:
            return self._unavailable(fallback)

        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        skipped_files: list[str] = []
        for index, file_path in enumerate([path for path in file_paths if path][:10], start=1):
            image_payload = _image_data_url(file_path)
            if image_payload is None:
                skipped_files.append(Path(file_path).name)
                continue
            content.append({"type": "text", "text": f"Страница {index} одного решения одной попытки:"})
            content.append({"type": "image_url", "image_url": {"url": image_payload}})

        if len(content) == 1:
            self._remember_error(
                f"Провайдер для {self.config.agent_label} не смог подготовить изображения для анализа."
            )
            return fallback

        if skipped_files:
            content.insert(
                1,
                {
                    "type": "text",
                    "text": f"Не удалось приложить файлы: {', '.join(skipped_files)}. Остальные страницы проверь как одно решение.",
                },
            )

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
            "max_tokens": 1800,
        }
        return self._post_chat_completion(payload, fallback)

    def _post_chat_completion(self, payload: dict[str, Any], fallback: str) -> str:
        if httpx is None:
            return self._unavailable(fallback)
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            return self._parse_chat_response(response, fallback)
        except httpx.TimeoutException as exc:
            self._remember_error(f"Таймаут запроса к {self.config.provider}: {exc}")
        except httpx.NetworkError as exc:
            self._remember_error(f"Сетевая ошибка при обращении к {self.config.provider}: {exc}")
        except httpx.HTTPStatusError as exc:
            self._remember_error(f"Ошибка {self.config.provider}: {exc.response.status_code}")
        except ValueError as exc:
            self._remember_error(f"Неверный формат ответа {self.config.provider}: {exc}")
        except Exception as exc:  # pragma: no cover
            self._remember_error(f"Неожиданная ошибка {self.config.provider}: {exc}")
        return fallback

    def _parse_chat_response(self, response: Any, fallback: str) -> str:
        if response.status_code in {401, 403}:
            self._remember_error(f"{self.config.provider} вернул ошибку авторизации. Проверьте токен.")
            return fallback
        if response.status_code == 429:
            self._remember_error(f"{self.config.provider} сообщил о превышении лимита запросов.")
            return fallback
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            self._remember_error(f"{self.config.provider} вернул пустой ответ.")
            return fallback
        self.last_error = None
        return content.strip()


class DeepSeekProvider(OpenAIProvider):
    name = "deepseek"
    supports_vision = False

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        self._remember_error(f"Провайдер для {self.config.agent_label} не поддерживает изображения.")
        return fallback


class GeminiProvider(AIProvider):
    name = "gemini"
    supports_vision = True

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        system_prompt, contents = _messages_to_gemini(messages)
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        return self._post_gemini(payload, fallback)

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        inline = _image_inline_data(file_path)
        if inline is None:
            self._remember_error(f"Провайдер для {self.config.agent_label} не поддерживает распознавание этого типа файла.")
            return fallback
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}, {"inline_data": inline}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
        }
        return self._post_gemini(payload, fallback)

    def _post_gemini(self, payload: dict[str, Any], fallback: str) -> str:
        if httpx is None:
            return self._unavailable(fallback)
        url = f"{self.config.base_url.rstrip('/')}/models/{self.config.model}:generateContent"
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(url, params={"key": self.config.api_key}, json=payload)
            if response.status_code in {401, 403}:
                self._remember_error("Gemini вернул ошибку авторизации. Проверьте токен.")
                return fallback
            if response.status_code == 429:
                self._remember_error("Gemini сообщил о превышении лимита запросов.")
                return fallback
            response.raise_for_status()
            data = response.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            content = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
            if not content.strip():
                self._remember_error("Gemini вернул пустой ответ.")
                return fallback
            self.last_error = None
            return content.strip()
        except httpx.TimeoutException as exc:
            self._remember_error(f"Таймаут запроса к Gemini: {exc}")
        except httpx.NetworkError as exc:
            self._remember_error(f"Сетевая ошибка при обращении к Gemini: {exc}")
        except httpx.HTTPStatusError as exc:
            self._remember_error(f"Ошибка Gemini: {exc.response.status_code}")
        except ValueError as exc:
            self._remember_error(f"Неверный формат ответа Gemini: {exc}")
        except Exception as exc:  # pragma: no cover
            self._remember_error(f"Неожиданная ошибка Gemini: {exc}")
        return fallback


class AnthropicProvider(AIProvider):
    name = "anthropic"
    supports_vision = True

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        system_prompt, prepared_messages = _messages_to_anthropic(messages)
        payload = {
            "model": self.config.model,
            "messages": prepared_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return self._post_anthropic(payload, fallback)

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        inline = _image_source_for_anthropic(file_path)
        if inline is None:
            self._remember_error(f"Провайдер для {self.config.agent_label} не поддерживает распознавание этого типа файла.")
            return fallback
        payload = {
            "model": self.config.model,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image", "source": inline},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1200,
        }
        return self._post_anthropic(payload, fallback)

    def _post_anthropic(self, payload: dict[str, Any], fallback: str) -> str:
        if httpx is None:
            return self._unavailable(fallback)
        url = f"{self.config.base_url.rstrip('/')}/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code in {401, 403}:
                self._remember_error("Anthropic вернул ошибку авторизации. Проверьте токен.")
                return fallback
            if response.status_code == 429:
                self._remember_error("Anthropic сообщил о превышении лимита запросов.")
                return fallback
            response.raise_for_status()
            data = response.json()
            parts = data.get("content", [])
            content = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")
            if not content.strip():
                self._remember_error("Anthropic вернул пустой ответ.")
                return fallback
            self.last_error = None
            return content.strip()
        except httpx.TimeoutException as exc:
            self._remember_error(f"Таймаут запроса к Anthropic: {exc}")
        except httpx.NetworkError as exc:
            self._remember_error(f"Сетевая ошибка при обращении к Anthropic: {exc}")
        except httpx.HTTPStatusError as exc:
            self._remember_error(f"Ошибка Anthropic: {exc.response.status_code}")
        except ValueError as exc:
            self._remember_error(f"Неверный формат ответа Anthropic: {exc}")
        except Exception as exc:  # pragma: no cover
            self._remember_error(f"Неожиданная ошибка Anthropic: {exc}")
        return fallback


class YandexGPTProvider(OpenAIProvider):
    name = "yandex_gpt"
    supports_vision = False

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        self.folder_id = _env_first(
            f"{config.env_prefix}_FOLDER_ID",
            "YANDEX_GPT_FOLDER_ID",
            "YANDEX_FOLDER_ID",
            default="",
        )

    @property
    def enabled(self) -> bool:
        return bool(
            not self.config.mock_mode
            and self.config.api_key
            and self.config.model
            and (self.folder_id or self.config.model.startswith("gpt://"))
            and httpx
        )

    def health_status(self) -> dict[str, Any]:
        base_status = super().health_status()
        if base_status["status"] in {"mock", "error"}:
            return base_status
        if not self.config.api_key:
            return base_status
        if not self.folder_id and not self.config.model.startswith("gpt://"):
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "fallback",
                "api_connected": False,
                "mock_mode": False,
                "message": f"Не найден YANDEX_FOLDER_ID или YANDEX_GPT_FOLDER_ID для {self.config.agent_label}.",
            }
        return {
            "provider": self.config.provider,
            "model": self._model_uri(),
            "status": "ok" if not self.last_error else "warning",
            "api_connected": True,
            "mock_mode": False,
            "message": self.last_error or f"YandexGPT настроен для {self.config.agent_label}.",
        }

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        payload = {
            "model": self._model_uri(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return self._post_chat_completion(payload, fallback)

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        self._remember_error("YandexGPT используется для текстовых агентов. Для распознавания файлов используется TextRecognitionAgent с Yandex OCR.")
        return fallback

    def _post_chat_completion(self, payload: dict[str, Any], fallback: str) -> str:
        if httpx is None:
            return self._unavailable(fallback)
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Api-Key {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.folder_id:
            headers["x-folder-id"] = self.folder_id
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            return self._parse_chat_response(response, fallback)
        except httpx.TimeoutException as exc:
            self._remember_error(f"Таймаут запроса к YandexGPT: {exc}")
        except httpx.NetworkError as exc:
            self._remember_error(f"Сетевая ошибка при обращении к YandexGPT: {exc}")
        except httpx.HTTPStatusError as exc:
            self._remember_error(f"Ошибка YandexGPT: {exc.response.status_code}: {_response_error_text(exc.response)}")
        except ValueError as exc:
            self._remember_error(f"Неверный формат ответа YandexGPT: {exc}")
        except Exception as exc:  # pragma: no cover
            self._remember_error(f"Неожиданная ошибка YandexGPT: {exc}")
        return fallback

    def _parse_chat_response(self, response: Any, fallback: str) -> str:
        if response.status_code in {401, 403}:
            self._remember_error(f"YandexGPT вернул ошибку авторизации: {_response_error_text(response)}")
            return fallback
        if response.status_code == 429:
            self._remember_error("YandexGPT сообщил о превышении лимита запросов.")
            return fallback
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            self._remember_error(f"YandexGPT вернул пустой ответ: {_response_error_text(response)}")
            return fallback
        self.last_error = None
        return content.strip()

    def _model_uri(self) -> str:
        model = (self.config.model or "").strip()
        if model.startswith("gpt://"):
            return model
        return f"gpt://{self.folder_id}/{model}"

    def _unavailable(self, fallback: str) -> str:
        if self.config.mock_mode:
            self._remember_error("AI_MOCK_MODE включен, YandexGPT не используется.")
        elif not self.config.api_key:
            self._remember_error(f"Не найден YANDEX_GPT_API_KEY для {self.config.agent_label}.")
        elif not self.folder_id and not self.config.model.startswith("gpt://"):
            self._remember_error(f"Не найден YANDEX_FOLDER_ID или YANDEX_GPT_FOLDER_ID для {self.config.agent_label}.")
        elif not self.config.model:
            self._remember_error(f"Модель YandexGPT для {self.config.agent_label} не указана.")
        elif httpx is None:
            self._remember_error("Библиотека httpx недоступна, YandexGPT не может быть вызван.")
        return fallback


class YandexOCRProvider(AIProvider):
    name = "yandex_ocr"
    supports_vision = True

    def __init__(self, config: AIProviderConfig) -> None:
        super().__init__(config)
        self.folder_id = _env_first(f"{config.env_prefix}_FOLDER_ID", "YANDEX_FOLDER_ID", default="")
        self.data_logging_enabled = _env_first("YANDEX_DATA_LOGGING_ENABLED", default="false").lower()

    @property
    def enabled(self) -> bool:
        return bool(
            not self.config.mock_mode
            and self.config.api_key
            and self.folder_id
            and self.config.model
            and httpx
        )

    def health_status(self) -> dict[str, Any]:
        base_status = super().health_status()
        if base_status["status"] in {"mock", "error"}:
            return base_status
        if not self.config.api_key:
            return base_status
        if not self.folder_id:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "status": "fallback",
                "api_connected": False,
                "mock_mode": False,
                "message": "Не найден YANDEX_FOLDER_ID для TextRecognitionAgent.",
            }
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "status": "ok" if not self.last_error else "warning",
            "api_connected": True,
            "mock_mode": False,
            "message": self.last_error or "Yandex OCR настроен для распознавания решений.",
        }

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        self._remember_error("Yandex OCR используется только для распознавания текста из файлов.")
        return fallback

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        if not self.enabled:
            return self._unavailable(fallback)
        mime_type = _file_to_yandex_mime(file_path)
        if mime_type is None:
            self._remember_error("Yandex OCR поддерживает только JPG, JPEG, PNG и PDF.")
            return fallback
        try:
            content = base64.b64encode(Path(file_path).read_bytes()).decode("utf-8")
        except OSError as exc:
            self._remember_error(f"Не удалось прочитать файл для Yandex OCR: {exc}")
            return fallback

        payload = {
            "mimeType": mime_type,
            "languageCodes": ["*"],
            "model": self.config.model or "page",
            "content": content,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.config.api_key}",
            "x-folder-id": self.folder_id,
            "x-data-logging-enabled": self.data_logging_enabled,
        }
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(self.config.base_url, headers=headers, json=payload)
            if response.status_code >= 400:
                self._remember_error(f"Yandex OCR вернул ошибку {response.status_code}: {_response_error_text(response)}")
                return fallback
            data = response.json()
            recognized_text = _extract_yandex_ocr_text(data)
            if not recognized_text:
                self._remember_error("Yandex OCR вернул пустой текст распознавания.")
                return fallback
            self.last_error = None
            return recognized_text
        except httpx.TimeoutException as exc:
            self._remember_error(f"Таймаут запроса к Yandex OCR: {exc}")
        except httpx.NetworkError as exc:
            self._remember_error(f"Сетевая ошибка при обращении к Yandex OCR: {exc}")
        except ValueError as exc:
            self._remember_error(f"Неверный формат ответа Yandex OCR: {exc}")
        except Exception as exc:  # pragma: no cover
            self._remember_error(f"Неожиданная ошибка Yandex OCR: {exc}")
        return fallback

    def _unavailable(self, fallback: str) -> str:
        if self.config.mock_mode:
            self._remember_error("AI_MOCK_MODE включен, Yandex OCR не используется.")
        elif not self.config.api_key:
            self._remember_error("Не найден YANDEX_API_KEY для TextRecognitionAgent.")
        elif not self.folder_id:
            self._remember_error("Не найден YANDEX_FOLDER_ID для TextRecognitionAgent.")
        elif not self.config.model:
            self._remember_error("Модель Yandex OCR не указана. Обычно используется TEXT_RECOGNITION_MODEL=page.")
        elif httpx is None:
            self._remember_error("Библиотека httpx недоступна, Yandex OCR не может быть вызван.")
        return fallback


class MockAIProvider(AIProvider):
    name = "mock"
    supports_vision = True

    def generate(self, messages: list[dict[str, Any]], fallback: str, temperature: float = 0.35, max_tokens: int = 1000) -> str:
        if self.config.unsupported_provider:
            self._remember_error(f"Провайдер {self.config.unsupported_provider} не поддерживается.")
        else:
            self._remember_error("AI_MOCK_MODE включен, реальные API не используются.")
        return fallback

    def vision_review(self, system_prompt: str, user_prompt: str, file_path: str, fallback: str) -> str:
        if self.config.unsupported_provider:
            self._remember_error(f"Провайдер {self.config.unsupported_provider} не поддерживает распознавание.")
        else:
            self._remember_error("AI_MOCK_MODE включен, распознавание выполнено в локальном тестовом режиме.")
        return fallback


PROVIDER_CLASSES: dict[str, type[AIProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "gemini": GeminiProvider,
    "anthropic": AnthropicProvider,
    "yandex_gpt": YandexGPTProvider,
    "yandex_ocr": YandexOCRProvider,
    "mock": MockAIProvider,
}


class AIClient:
    """Клиент конкретного агента: выбирает провайдера, модель и ключ из конфигурации."""

    def __init__(self, config: AIProviderConfig | None = None) -> None:
        self.config = config or AIClientFactory.config_for_agent("tutor_chat")
        provider_class = PROVIDER_CLASSES.get(self.config.provider, MockAIProvider)
        self.provider = provider_class(self.config)

    @property
    def enabled(self) -> bool:
        return self.provider.enabled

    @property
    def last_error(self) -> str | None:
        return self.provider.last_error

    @property
    def provider_name(self) -> str:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    def health_status(self) -> dict[str, Any]:
        return self.provider.health_status()

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        context: str | dict[str, Any] | None = None,
        fallback: str | None = None,
    ) -> str:
        fallback_text = fallback or self._generic_fallback(system_prompt, user_prompt)
        context_text = self._format_context(context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context_text}\n\n{user_prompt}".strip()},
        ]
        return self.provider.generate(messages, fallback_text)

    def chat(self, system_prompt: str, messages: list[dict[str, str]], fallback: str) -> str:
        prepared_messages = [{"role": "system", "content": system_prompt}, *messages]
        return self.provider.generate(prepared_messages, fallback)

    def chat_with_tutor(
        self,
        message: str,
        course: Any = None,
        topic: Any = None,
        task: Any = None,
        chat_history: list[dict[str, str]] | None = None,
        fallback: str | None = None,
    ) -> str:
        system_prompt = (
            "Ты ИИ-тьютор по математике для подготовки к ОГЭ и ЕГЭ. "
            "Помогай ученику понять идею решения, задавай наводящие вопросы и не выдавай готовый ответ без объяснения."
        )
        context = {
            "курс": getattr(course, "title", None),
            "тема": getattr(topic, "title", None),
            "задание": getattr(task, "condition_text", None),
            "критерии": getattr(task, "criteria", None),
            "материал темы": self._topic_material_context(topic),
            "последние сообщения": chat_history or [],
        }
        fallback_text = fallback or (
            "Давайте разберём задание по шагам: сначала определим тип задачи, затем выпишем данные, выберем метод и проверим ответ."
        )
        return self.generate_text(system_prompt, message, context=context, fallback=fallback_text)

    @staticmethod
    def _topic_material_context(topic: Any = None) -> dict[str, str] | None:
        materials = getattr(topic, "materials", None)
        if not materials:
            return None
        material = materials[0]
        return {
            "название": getattr(material, "title", ""),
            "объяснение": getattr(material, "content", ""),
            "пример": getattr(material, "examples", ""),
        }

    def analyze_solution(
        self,
        task: Any,
        student_answer: str | None = None,
        recognized_text: str | None = None,
        criteria: str | None = None,
        attempt_history: list[Any] | None = None,
        fallback: str | None = None,
    ) -> str:
        system_prompt = (
            "Ты эксперт по проверке решений ОГЭ и ЕГЭ по математике. "
            "Сравни решение ученика с эталонным решением, правильным ответом и критериями оценивания. "
            "Анализируй не только итоговый ответ, но и ход решения ученика. "
            "Проверяй соответствие критериям экзамена, указывай математические ошибки, логические пробелы и недочёты оформления. "
            "Не занижай и не завышай результат. Если решение неполное, объясни, что нужно добавить. "
            "Ответь обычным русским текстом без Markdown, без LaTeX-разметки и без символов $."
            "Структура ответа: 1) оценка решения; 2) что исправить; 3) следующий шаг. "
            "Пиши кратко: максимум 5 предложений."
        )
        history_text = [
            {
                "попытка": getattr(item, "attempt_number", None),
                "ответ": getattr(item, "extracted_answer", None),
                "верно": getattr(item, "is_correct", None),
                "балл": getattr(item, "score", None),
            }
            for item in (attempt_history or [])
        ]
        context = {
            "условие": getattr(task, "condition_text", ""),
            "правильный ответ": getattr(task, "correct_answer", ""),
            "эталонное решение": _task_reference_solution(task),
            "критерии": criteria or getattr(task, "criteria", ""),
            "текстовый ответ ученика": student_answer or "",
            "распознанный текст": recognized_text or "",
            "история предыдущих попыток": history_text,
        }
        fallback_text = fallback or "Решение принято к анализу. Проверьте вычисления, оформление и соответствие критериям."
        return self.generate_text(system_prompt, "Проанализируй решение ученика.", context=context, fallback=fallback_text)

    def analyze_solution_images(
        self,
        task: Any,
        solution_file_paths: list[str],
        reference_file_path: str | None = None,
        reference_file_paths: list[str] | None = None,
        criteria: str | None = None,
        attempt_history: list[Any] | None = None,
        fallback: str | None = None,
    ) -> str:
        fallback_text = fallback or (
            "Решение сохранено. Для развёрнутой части требуется проверка преподавателя по загруженным страницам решения."
        )
        if not solution_file_paths:
            return fallback_text
        if not getattr(self.provider, "supports_vision", False):
            self.provider._remember_error(
                f"Провайдер {self.config.provider} не поддерживает прямую проверку фото решения."
            )
            return fallback_text

        system_prompt = (
            "Ты эксперт по проверке развёрнутых решений ОГЭ и ЕГЭ по математике. "
            "Проверяй ход решения по изображению, сравнивай с правильным ответом, критериями и эталонным решением. "
            "Если загружено несколько изображений, считай их страницами одного общего решения одной попытки, а не разными решениями одного задания. "
            "Объединяй ход рассуждений со всех страниц и делай один общий вывод по попытке. "
            "Не переписывай весь текст с фото. Дай краткий комментарий: что верно, где именно ошибка или недочёт, что нужно исправить. "
            "Если проблема в оформлении, укажи конкретный фрагмент: например первая строка, переход к ответу, проверка корней, вторая страница, рисунок или обоснование. "
            "Пиши обычным русским текстом без Markdown и LaTeX-разметки."
        )
        reference_note = f"Текстовое эталонное решение: {_task_reference_solution(task)}"
        reference_paths = [path for path in (reference_file_paths or []) if path]
        if not reference_paths and reference_file_path:
            reference_paths = [reference_file_path]
        if reference_paths:
            reference_prompt = (
                "На изображении страница эталонного решения задания. Кратко извлеки ход решения, ключевые шаги и итоговый ответ. "
                "Если файл нечитаем, так и напиши."
            )
            reference_reviews = []
            for index, path in enumerate(reference_paths[:5], start=1):
                reference_review = self.provider.vision_review(system_prompt, f"{reference_prompt}\nСтраница эталона: {index}.", path, "")
                if reference_review.strip():
                    reference_reviews.append(f"страница {index}: {reference_review.strip()}")
            reference_note = (
                f"Эталонное решение по файлам: {'; '.join(reference_reviews)}"
                if reference_reviews
                else "Эталонное решение загружено файлом, но vision-провайдер не смог его прочитать."
            )
        history_text = [
            f"попытка {getattr(item, 'attempt_number', '-')}: балл={getattr(item, 'score', None)}, верно={getattr(item, 'is_correct', None)}"
            for item in (attempt_history or [])
        ]
        solution_paths = [path for path in solution_file_paths if path][:10]
        page_list = "\n".join(f"Страница {index}: {Path(path).name}" for index, path in enumerate(solution_paths, start=1))
        prompt = (
            "Проверь загруженные изображения как одно цельное решение одной попытки ученика.\n"
            "Важно: страница 1, страница 2 и следующие страницы являются продолжением одного и того же решения. "
            "Не называй их разными решениями и не делай отдельные независимые выводы по каждой странице.\n"
            f"Порядок страниц:\n{page_list}\n"
            f"Условие: {getattr(task, 'condition_text', '')}\n"
            f"Правильный ответ: {getattr(task, 'correct_answer', '')}\n"
            f"Критерии: {criteria or getattr(task, 'criteria', '')}\n"
            f"{reference_note}\n"
            f"История попыток: {'; '.join(history_text) or 'нет'}\n"
            "Дай один общий комментарий по всей попытке: что решено верно, где конкретная проблема, что нужно исправить. "
            "Если фрагмент нечитаем, укажи номер страницы и место на ней, но не считай это отдельным решением."
        )
        review = self.provider.vision_review_many(system_prompt, prompt, solution_paths, "")
        if review.strip():
            return review.strip()
        return fallback_text

    def recognize_text_from_file(self, file_path: str | None) -> str:
        if not file_path:
            return ""
        health = self.health_status()
        fallback = f"Файл решения сохранён. Распознавание не выполнено через {self.config.provider}: {health.get('message', 'проверьте настройки API')}."
        system_prompt = (
            "Ты агент распознавания текста из решения по математике. "
            "Извлеки читаемый текст, формулы и итоговый ответ. Не оценивай решение."
        )
        user_prompt = "Распознай текст решения с изображения. Если часть текста не читается, отметь это явно."
        recognized = self.provider.vision_review(system_prompt, user_prompt, file_path, fallback)
        if recognized == fallback and self.last_error and self.last_error not in recognized:
            return f"{recognized} Причина: {self.last_error}"
        return recognized

    def generate_similar_task(self, task: Any, topic: Any = None, difficulty: str | None = None, fallback: str | None = None) -> str:
        prompt = (
            "Составь похожее задание по математике с тем же проверяемым навыком. "
            "Измени числа и формулировку, добавь правильный ответ и краткое решение."
        )
        context = {
            "исходное условие": getattr(task, "condition_text", ""),
            "тема": getattr(topic, "title", None) or getattr(getattr(task, "topic", None), "title", None),
            "сложность": difficulty or getattr(task, "difficulty", ""),
            "ответ": getattr(task, "correct_answer", ""),
        }
        return self.generate_text(
            "Ты составляешь задания в стиле ОГЭ и ЕГЭ по математике.",
            prompt,
            context=context,
            fallback=fallback or "",
        )

    def cheap_classify(self, message: str, fallback: dict[str, Any]) -> dict[str, Any]:
        text = self.generate_text(
            "Верни строгий JSON с полями allowed, reason, detected_topic. Разрешай только учебные вопросы по математике.",
            message,
            fallback=json.dumps(fallback, ensure_ascii=False),
        )
        try:
            parsed = json.loads(_extract_json(text))
            return {
                "allowed": bool(parsed.get("allowed", fallback.get("allowed", True))),
                "reason": str(parsed.get("reason", fallback.get("reason", "")))[:500],
                "detected_topic": str(parsed.get("detected_topic", fallback.get("detected_topic", "математика"))),
            }
        except (TypeError, ValueError) as exc:
            self.provider._remember_error(f"Неверный формат ответа классификатора: {exc}")
            return fallback

    def summarize(self, text: str, fallback: str) -> str:
        return self.generate_text(
            "Сделай краткое содержание диалога ученика с ИИ-тьютором. Сохрани темы, ошибки, цели и рекомендации.",
            text,
            fallback=fallback,
        )

    def generate_task(self, prompt: str, fallback: str) -> str:
        return self.generate_text(
            "Ты составляешь похожие задания в стиле ОГЭ и ЕГЭ по математике.",
            prompt,
            fallback=fallback,
        )

    @staticmethod
    def _format_context(context: str | dict[str, Any] | None) -> str:
        if context is None:
            return ""
        if isinstance(context, str):
            return context
        return json.dumps(context, ensure_ascii=False, default=str)

    @staticmethod
    def _generic_fallback(system_prompt: str, user_prompt: str) -> str:
        lower_prompt = f"{system_prompt} {user_prompt}".lower()
        if "провер" in lower_prompt or "решени" in lower_prompt:
            return "Решение сохранено. Проверьте вычисления, оформление ответа и соответствие критериям задания."
        if "тьютор" in lower_prompt or "объяс" in lower_prompt:
            return "Разберём тему по шагам: определим тип задания, выпишем данные, выберем метод решения и проверим ответ."
        return "ИИ-сервис сейчас недоступен, поэтому сформирован локальный учебный ответ."


class AIClientFactory:
    """Фабрика клиентов: каждый агент получает своего провайдера и модель из `.env`."""

    @classmethod
    def create_for_agent(cls, agent_name: str) -> AIClient:
        return AIClient(cls.config_for_agent(agent_name))

    @classmethod
    def createForAgent(cls, agent_name: str) -> AIClient:
        return cls.create_for_agent(agent_name)

    @classmethod
    def config_for_agent(cls, agent_name: str) -> AIProviderConfig:
        normalized = cls._normalize_agent_name(agent_name)
        settings = AGENT_SETTINGS[normalized]
        prefix = settings["env_prefix"]
        provider = _normalize_provider(
            _env_first(
                f"{prefix}_PROVIDER",
                "AI_PROVIDER",
                default=settings["default_provider"],
            )
        )
        mock_mode = _env_bool("AI_MOCK_MODE", False) or provider == "mock"
        unsupported_provider = None if provider in PROVIDER_CLASSES else provider
        if unsupported_provider:
            provider = "mock"
            mock_mode = False

        model = _env_first(f"{prefix}_MODEL", "AI_MODEL", "AI_MODEL_MAIN", default=settings["default_model"])
        api_key = cls._agent_api_key(prefix, provider)
        base_url = cls._agent_base_url(prefix, provider)
        timeout = _env_float("AI_TIMEOUT_SECONDS", 30.0)
        return AIProviderConfig(
            agent_key=normalized,
            agent_label=settings["label"],
            env_prefix=prefix,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            mock_mode=mock_mode,
            unsupported_provider=unsupported_provider,
        )

    @classmethod
    def health(cls) -> dict[str, Any]:
        result = {}
        for agent_key in AGENT_SETTINGS:
            client = cls.create_for_agent(agent_key)
            result[_camel_agent_key(agent_key)] = client.health_status()
        return result

    @staticmethod
    def _normalize_agent_name(agent_name: str) -> str:
        key = (agent_name or "").strip().lower().replace("-", "_")
        key = AGENT_ALIASES.get(key, key)
        if key not in AGENT_SETTINGS:
            raise ValueError(f"Неизвестный ИИ-агент: {agent_name}")
        return key

    @staticmethod
    def _agent_api_key(prefix: str, provider: str) -> str:
        provider_key_env = PROVIDER_KEY_ENV.get(provider, "")
        keys = [f"{prefix}_API_KEY"]
        if provider_key_env:
            keys.append(provider_key_env)
        if provider in {"yandex_ocr", "yandex_gpt"}:
            return _env_first(*keys, default="")
        # Backward compatibility with the previous single-client configuration.
        keys.extend(["POLZA_API_KEY", "AI_API_KEY", "OPENAI_API_KEY"])
        return _env_first(*keys, default="")

    @staticmethod
    def _agent_base_url(prefix: str, provider: str) -> str:
        provider_base_env = PROVIDER_BASE_ENV.get(provider, "")
        keys = [f"{prefix}_BASE_URL"]
        if provider_base_env:
            keys.append(provider_base_env)
        keys.append("AI_BASE_URL")
        return _env_first(*keys, default=PROVIDER_DEFAULT_BASE_URLS.get(provider, "")).rstrip("/")


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _normalize_provider(provider: str) -> str:
    value = (provider or "mock").strip().lower().replace("_", "-")
    aliases = {
        "openai-compatible": "openai",
        "openai_compatible": "openai",
        "chatgpt": "openai",
        "google": "gemini",
        "claude": "anthropic",
        "yandex-gpt": "yandex_gpt",
        "yandexgpt": "yandex_gpt",
        "yandex-ai": "yandex_gpt",
        "yandex-ai-studio": "yandex_gpt",
        "yandex-cloud-gpt": "yandex_gpt",
        "yandex-foundation-models": "yandex_gpt",
        "foundation-models": "yandex_gpt",
        "language-models": "yandex_gpt",
        "yandex": "yandex_ocr",
        "yandex-ocr": "yandex_ocr",
        "yandex_cloud_ocr": "yandex_ocr",
        "yandex-cloud-ocr": "yandex_ocr",
        "yandexvision": "yandex_ocr",
        "yandex-vision": "yandex_ocr",
        "test": "mock",
    }
    return aliases.get(value, value)


def _camel_agent_key(agent_key: str) -> str:
    parts = agent_key.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _extract_json(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _task_reference_solution(task: Any) -> str:
    solution = getattr(task, "solution", None) or getattr(task, "solution_explanation", None)
    if solution:
        return str(solution)
    return "Эталонное решение пока не заполнено. Сравнивайте по правильному ответу и критериям."


def _messages_to_gemini(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_prompt = ""
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", ""))
        if role == "system":
            system_prompt = f"{system_prompt}\n{content}".strip()
            continue
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": content}]})
    if not contents:
        contents.append({"role": "user", "parts": [{"text": ""}]})
    return system_prompt, contents


def _messages_to_anthropic(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_prompt = ""
    prepared: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", ""))
        if role == "system":
            system_prompt = f"{system_prompt}\n{content}".strip()
            continue
        prepared.append({"role": "assistant" if role == "assistant" else "user", "content": content})
    if not prepared:
        prepared.append({"role": "user", "content": ""})
    return system_prompt, prepared


def _image_data_url(file_path: str) -> str | None:
    path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _image_inline_data(file_path: str) -> dict[str, str] | None:
    path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return {"mime_type": mime_type, "data": encoded}


def _image_source_for_anthropic(file_path: str) -> dict[str, str] | None:
    inline = _image_inline_data(file_path)
    if inline is None:
        return None
    return {"type": "base64", "media_type": inline["mime_type"], "data": inline["data"]}


def _file_to_yandex_mime(file_path: str) -> str | None:
    extension = Path(file_path).suffix.lower()
    mapping = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".pdf": "PDF",
    }
    return mapping.get(extension)


def _extract_yandex_ocr_text(data: dict[str, Any]) -> str:
    annotation = data.get("result", {}).get("textAnnotation", {})
    full_text = annotation.get("fullText") or annotation.get("text")
    if isinstance(full_text, str) and full_text.strip():
        return full_text.strip()

    text_items: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                text_items.append(text.strip())
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(annotation or data)
    unique_items = list(dict.fromkeys(text_items))
    return "\n".join(unique_items).strip()


def _response_error_text(response: Any) -> str:
    try:
        data = response.json()
    except ValueError:
        return str(getattr(response, "text", "") or "").strip()[:700] or "пустой ответ сервиса"
    if isinstance(data, dict):
        parts = []
        for key in ("message", "error", "error_description", "details", "code"):
            value = data.get(key)
            if value:
                parts.append(f"{key}: {value}")
        if parts:
            return "; ".join(parts)[:700]
        return json.dumps(data, ensure_ascii=False, default=str)[:700]
    return str(data)[:700]
