"""
Mistral OCR vision provider using the dedicated ``/v1/ocr`` endpoint.

Calls Mistral's OCR service (model ``mistral-ocr-latest``) over REST via the
existing ``httpx`` dependency — NOT the standard chat-completions endpoint.
Images are supplied as base64 ``data:`` URLs. The OCR response returns per-page
markdown which we concatenate into plain text.
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

_MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"


class MistralProvider(BaseVisionProvider):

    def __init__(self, api_key: str, model_id: str | None = None, **kwargs):
        super().__init__(api_key=api_key, model_id=model_id, **kwargs)
        self.provider_name = "MISTRAL"
        self._httpx = None

        try:
            import httpx
            self._httpx = httpx
            # A truthy client sentinel so is_configured() passes; real requests
            # open short-lived clients to keep the provider stateless/thread-safe.
            self.client = httpx
        except ImportError:
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning("[MISTRAL] init failed: %s", e)
            self.client = None

    # ------------------------------------------------------------------
    # Internal call
    # ------------------------------------------------------------------
    def _ocr(self, image_bytes: bytes, mime_type: str) -> str | None:
        httpx = self._httpx
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        payload = {
            "model": self.model_id,
            "document": {
                "type": "image_url",
                "image_url": data_url,
            },
            "include_image_base64": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        def _call():
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(_MISTRAL_OCR_URL, json=payload, headers=headers)
            except httpx.TimeoutException as e:
                raise RetryableError(f"timeout: {e}")
            except httpx.TransportError as e:
                raise RetryableError(f"transport error: {e}")

            if resp.status_code in {408, 409, 429, 500, 502, 503, 504}:
                raise RetryableError(
                    f"HTTP {resp.status_code}",
                    retry_after=self._parse_retry_after(resp.headers),
                )
            resp.raise_for_status()

            data = resp.json()
            return self._extract_text(data)

        return self._run_with_retries(_call)

    @staticmethod
    def _extract_text(data: dict) -> str | None:
        if not isinstance(data, dict):
            return None
        pages = data.get("pages")
        if isinstance(pages, list) and pages:
            parts = []
            for page in pages:
                if isinstance(page, dict):
                    md = page.get("markdown") or page.get("text")
                    if md:
                        parts.append(md.strip())
            joined = "\n\n".join(p for p in parts if p)
            return joined or None
        # Fallbacks for alternate response shapes
        for key in ("markdown", "text", "content"):
            value = data.get(key)
            if value:
                return str(value).strip()
        return None

    # ------------------------------------------------------------------
    # Public API — OCR handles both single images and full pages.
    # ------------------------------------------------------------------
    def describe_image(self, image_bytes: bytes, mime_type: str = "image/jpeg",
                       prompt: str | None = None,
                       metadata: dict[str, Any] | None = None) -> VisionResult | None:
        if not self.is_configured() or self._too_large(image_bytes):
            return None
        text = self._ocr(image_bytes, mime_type)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})

    def describe_page(self, image_bytes: bytes, mime_type: str = "image/jpeg",
                      prompt: str | None = None,
                      metadata: dict[str, Any] | None = None) -> VisionResult | None:
        if not self.is_configured() or self._too_large(image_bytes):
            return None
        text = self._ocr(image_bytes, mime_type)
        if not text:
            return None
        return VisionResult(text=text, provider=self.provider_name,
                            model=self.model_id, metadata=metadata or {})
