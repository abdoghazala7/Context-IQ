from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VisionResult:
    """
    Normalized result returned by every vision provider.

    Attributes
    ----------
    text : str
        The extracted/described text (image caption or OCR output).
    provider : str
        The provider selector that produced this result (e.g. "GEMINI").
    model : str | None
        The concrete model id used for the call.
    metadata : dict[str, Any]
        Free-form provider metadata (usage, timing, retries, etc.).
    """
    text: str
    provider: str
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionInterface(ABC):
    """
    Shared contract for all vision providers.

    Implementations MUST be resilient: any misconfiguration, SDK error,
    rate-limit exhaustion, or oversized payload should result in returning
    ``None`` (skip enrichment) rather than raising, so PDF text/table
    processing is never blocked by the optional vision layer.
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the provider has a usable client + credentials."""
        pass

    @abstractmethod
    def set_vision_model(self, model_id: str | None = None) -> None:
        """Set/override the active model id for subsequent calls."""
        pass

    @abstractmethod
    def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionResult | None:
        """Describe a single embedded image for retrieval. None on skip/failure."""
        pass

    @abstractmethod
    def describe_page(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionResult | None:
        """OCR/describe a full rendered page. None on skip/failure."""
        pass


class NullVisionProvider(VisionInterface):
    """
    No-op fallback returned by the factory whenever vision is unset,
    invalid, or unconfigured. It is always safe to call and never raises.

    This guarantees the ingestion pipeline can always hold a non-None
    ``vision_client`` without gating startup on provider availability.
    """

    def __init__(self, reason: str | None = None):
        self.reason = reason or "vision provider not configured"

    def is_configured(self) -> bool:
        return False

    def set_vision_model(self, model_id: str | None = None) -> None:
        return None

    def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionResult | None:
        return None

    def describe_page(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionResult | None:
        return None
