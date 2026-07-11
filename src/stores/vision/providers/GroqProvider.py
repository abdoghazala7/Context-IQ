"""
Groq vision provider — handles both Groq multimodal models:
  * meta-llama/llama-4-scout-17b-16e-instruct   (GROQ_LLAMA_SCOUT)
  * qwen/qwen3.6-27b                             (GROQ_QWEN)

Reuses the existing ``groq`` SDK and the shared ``GROQ_API_KEY``. Images are
passed as base64 ``data:`` URLs inside multimodal chat messages.
"""

import base64
from typing import Any

from ..VisionInterface import VisionResult
from ._base import (
    BaseVisionProvider,
    RetryableError,
    DEFAULT_IMAGE_PROMPT,
    DEFAULT_PAGE_PROMPT,
)


class GroqProvider(BaseVisionProvider):

    def __init__(self, api_key: str, model_id: str | None = None, **kwargs):
        super().__init__(api_key=api_key, model_id=model_id, **kwargs)
        self.provider_name = "GROQ"

        try:
            from groq import Groq
            self.client = Groq(api_key=self.api_key, timeout=self.timeout_seconds)
        except ImportError:
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning("[GROQ] client init failed: %s", e)
            self.client = None

    # ------------------------------------------------------------------
    # Internal call
    # ------------------------------------------------------------------
    def _chat_vision(self, image_bytes: bytes, mime_type: str, prompt: str) -> str | None:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        def _call():
            try:
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    temperature=0.0,
                )
            except Exception as e:  # noqa: BLE001 - classify transient vs fatal
                if self._is_retryable(e):
                    raise RetryableError(str(e), retry_after=self._retry_after_from_exc(e))
                raise

            if (not response or not response.choices or len(response.choices) == 0
                    or not response.choices[0].message):
                return None
            content = response.choices[0].message.content
            return content.strip() if content else None

        return self._run_with_retries(_call)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if code in {408, 409, 429, 500, 502, 503, 504}:
            return True
        text = str(exc).lower()
        return any(
            token in text
            for token in ("rate limit", "429", "timeout", "unavailable",
                          "503", "500", "502", "504", "connection", "overloaded")
        )

    @staticmethod
    def _retry_after_from_exc(exc: Exception):
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) or getattr(exc, "headers", None)
        if headers:
            try:
                value = headers.get("Retry-After") or headers.get("retry-after")
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def describe_image(self, image_bytes: bytes, mime_type: str = "image/jpeg",
                       prompt: str | None = None,
                       metadata: dict[str, Any] | None = None) -> VisionResult | None:
        if not self.is_configured() or self._too_large(image_bytes):
            return None
        text = self._chat_vision(image_bytes, mime_type, prompt or DEFAULT_IMAGE_PROMPT)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})

    def describe_page(self, image_bytes: bytes, mime_type: str = "image/jpeg",
                      prompt: str | None = None,
                      metadata: dict[str, Any] | None = None) -> VisionResult | None:
        if not self.is_configured() or self._too_large(image_bytes):
            return None
        text = self._chat_vision(image_bytes, mime_type, prompt or DEFAULT_PAGE_PROMPT)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})
