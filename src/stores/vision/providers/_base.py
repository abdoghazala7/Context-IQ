"""
Shared base utilities for vision providers.

Provides a resilient retry/backoff wrapper so that transient API failures
(429/408/409/5xx, connection errors, timeouts) are retried *inside* the
provider call. This keeps Celery from retrying an entire file just because a
single image request hit a rate limit. All hard failures ultimately return
``None`` (skip enrichment) rather than raising, per the vision layer contract.
"""

import time
import random
import logging
from typing import Callable, Optional

from ..VisionInterface import VisionInterface

logger = logging.getLogger(__name__)

# HTTP status codes worth retrying.
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}

# Default prompts (providers may accept an override per-call).
DEFAULT_IMAGE_PROMPT = (
    "Describe the visual content for retrieval. Include visible text, chart "
    "axes/labels, entities, and concise semantic meaning. Do not hallucinate "
    "unseen details."
)
DEFAULT_PAGE_PROMPT = (
    "Extract all readable text in natural reading order. Preserve headings, "
    "lists, tables, and labels."
)


class RetryableError(Exception):
    """Raised internally to signal a transient, retryable failure."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class BaseVisionProvider(VisionInterface):
    """
    Common construction + retry behaviour for concrete vision providers.

    Subclasses set ``self.client`` (or leave it None to be "not configured")
    and implement ``describe_image`` / ``describe_page`` using
    :meth:`_run_with_retries` around their actual API call.
    """

    def __init__(
        self,
        api_key: str,
        model_id: str | None = None,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        max_image_bytes: int = 4_000_000,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.max_image_bytes = max_image_bytes

        self.provider_name = "BASE"
        self.client = None
        self.logger = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)

    # ------------------------------------------------------------------
    # Interface defaults
    # ------------------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.client is not None and bool(self.model_id)

    def set_vision_model(self, model_id: str | None = None) -> None:
        if model_id:
            self.model_id = model_id

    # ------------------------------------------------------------------
    # Guardrails
    # ------------------------------------------------------------------
    def _too_large(self, image_bytes: bytes) -> bool:
        if image_bytes is None:
            return True
        if len(image_bytes) > self.max_image_bytes:
            self.logger.warning(
                "[%s] image payload %d bytes exceeds VISION_MAX_IMAGE_BYTES=%d; skipping.",
                self.provider_name, len(image_bytes), self.max_image_bytes,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Retry engine
    # ------------------------------------------------------------------
    def _sleep_backoff(self, attempt: int, retry_after: Optional[float]) -> None:
        if retry_after is not None and retry_after >= 0:
            delay = retry_after
        else:
            # exponential backoff with full jitter
            delay = self.retry_base_seconds * (2 ** attempt)
            delay = random.uniform(0, delay)
        # cap the individual sleep to avoid pathological waits
        delay = min(delay, 30.0)
        self.logger.info(
            "[%s] retrying after %.2fs (attempt %d/%d).",
            self.provider_name, delay, attempt + 1, self.max_retries,
        )
        time.sleep(delay)

    def _run_with_retries(self, call: Callable[[], "object"]):
        """
        Execute ``call`` with retry/backoff. ``call`` should raise
        :class:`RetryableError` for transient failures. Any other exception is
        treated as fatal-for-this-item and results in ``None`` being returned.
        """
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return call()
            except RetryableError as e:
                last_error = e
                if attempt >= self.max_retries:
                    break
                self._sleep_backoff(attempt, e.retry_after)
            except Exception as e:  # noqa: BLE001 - non-retryable, skip this item
                self.logger.warning(
                    "[%s] non-retryable vision error: %s", self.provider_name, e
                )
                return None

        self.logger.warning(
            "[%s] exhausted retries (%d). Last error: %s",
            self.provider_name, self.max_retries, last_error,
        )
        return None

    # ------------------------------------------------------------------
    # Retry-After parsing helper
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_retry_after(headers) -> Optional[float]:
        if not headers:
            return None
        try:
            value = headers.get("Retry-After") or headers.get("retry-after")
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
