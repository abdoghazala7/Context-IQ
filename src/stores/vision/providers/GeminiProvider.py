"""
Gemini vision provider (Gemini 3.5 Flash) using the modern ``google-genai`` SDK.

Uses ``from google import genai`` + ``genai.Client`` conventions (NOT the
legacy ``google-generativeai`` package). Image bytes are sent as inline
``types.Part.from_bytes`` parts alongside the text prompt.
"""

from typing import Any

from ..VisionInterface import VisionResult
from ._base import (
    BaseVisionProvider,
    RetryableError,
    DEFAULT_IMAGE_PROMPT,
    DEFAULT_PAGE_PROMPT,
)


class GeminiProvider(BaseVisionProvider):

    def __init__(self, api_key: str, model_id: str | None = None, **kwargs):
        super().__init__(api_key=api_key, model_id=model_id, **kwargs)
        self.provider_name = "GEMINI"
        self._types = None

        try:
            # Modern SDK: `pip install google-genai`
            from google import genai
            from google.genai import types

            self._types = types
            # http_options carries the request timeout (milliseconds).
            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
            )
        except ImportError:
            # Re-raise so the factory can lazily fall back to NullVisionProvider.
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning("[GEMINI] client init failed: %s", e)
            self.client = None

    # ------------------------------------------------------------------
    # Internal call
    # ------------------------------------------------------------------
    def _generate(self, image_bytes: bytes, mime_type: str, prompt: str) -> str | None:
        types = self._types

        def _call():
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        prompt,
                    ],
                )
            except Exception as e:  # noqa: BLE001 - classify transient vs fatal
                if self._is_retryable(e):
                    raise RetryableError(str(e), retry_after=self._retry_after_from_exc(e))
                raise

            text = getattr(response, "text", None)
            if text:
                return text.strip()
            return None

        return self._run_with_retries(_call)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code in {408, 409, 429, 500, 502, 503, 504}:
            return True
        text = str(exc).lower()
        return any(
            token in text
            for token in ("rate limit", "429", "deadline", "timeout", "unavailable",
                          "503", "500", "502", "504", "connection")
        )

    @staticmethod
    def _retry_after_from_exc(exc: Exception):
        headers = getattr(exc, "response_headers", None) or getattr(exc, "headers", None)
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
        text = self._generate(image_bytes, mime_type, prompt or DEFAULT_IMAGE_PROMPT)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})

    def describe_page(self, image_bytes: bytes, mime_type: str = "image/jpeg",
                      prompt: str | None = None,
                      metadata: dict[str, Any] | None = None) -> VisionResult | None:
        if not self.is_configured() or self._too_large(image_bytes):
            return None
        text = self._generate(image_bytes, mime_type, prompt or DEFAULT_PAGE_PROMPT)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})
