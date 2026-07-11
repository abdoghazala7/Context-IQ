import logging

from .VisionEnums import VisionEnums, DEFAULT_VISION_MODELS
from .VisionInterface import VisionInterface, NullVisionProvider

logger = logging.getLogger(__name__)


class VisionProviderFactory:
    """
    Creates a configured vision provider from application settings.

    Design guarantees
    -----------------
    * NEVER raises and NEVER returns ``None`` — on any problem (unset/invalid
      selector, missing key, missing SDK, construction error) it returns a
      :class:`NullVisionProvider` so the ingestion pipeline can always hold a
      safe, callable ``vision_client``.
    * Provider modules are imported lazily inside :meth:`create` so that a
      missing optional SDK (e.g. ``google-genai``) cannot break app/worker
      startup for deployments that don't use vision.
    """

    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_model_id(self, provider: str) -> str | None:
        """Prefer the explicit override, else the provider's default model."""
        override = getattr(self.config, "VISION_MODEL_ID", None)
        if override:
            return override
        return DEFAULT_VISION_MODELS.get(provider)

    def _common_kwargs(self) -> dict:
        """Shared tuning knobs passed to every real provider."""
        return {
            "timeout_seconds": getattr(self.config, "VISION_TIMEOUT_SECONDS", 60),
            "max_retries": getattr(self.config, "VISION_MAX_RETRIES", 3),
            "retry_base_seconds": getattr(self.config, "VISION_RETRY_BASE_SECONDS", 1.0),
            "max_image_bytes": getattr(self.config, "VISION_MAX_IMAGE_BYTES", 4_000_000),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create(self, provider: str | None = None) -> VisionInterface:
        provider = (provider or getattr(self.config, "VISION_PROVIDER", None) or "").strip().upper()

        if not provider:
            logger.info("VISION_PROVIDER not set; vision layer disabled (NullVisionProvider).")
            return NullVisionProvider(reason="VISION_PROVIDER not set")

        valid = {e.value for e in VisionEnums}
        if provider not in valid:
            logger.warning(
                "Invalid VISION_PROVIDER '%s'. Valid: %s. Falling back to NullVisionProvider.",
                provider, ", ".join(sorted(valid)),
            )
            return NullVisionProvider(reason=f"invalid VISION_PROVIDER '{provider}'")

        model_id = self._resolve_model_id(provider)
        common = self._common_kwargs()

        try:
            if provider == VisionEnums.GEMINI.value:
                api_key = getattr(self.config, "GEMINI_API_KEY", None)
                if not api_key:
                    return NullVisionProvider(reason="GEMINI_API_KEY missing")
                from .providers import GeminiProvider
                client = GeminiProvider(api_key=api_key, model_id=model_id, **common)

            elif provider == VisionEnums.MISTRAL.value:
                api_key = getattr(self.config, "MISTRAL_API_KEY", None)
                if not api_key:
                    return NullVisionProvider(reason="MISTRAL_API_KEY missing")
                from .providers import MistralProvider
                client = MistralProvider(api_key=api_key, model_id=model_id, **common)

            elif provider in (VisionEnums.GROQ_LLAMA_SCOUT.value, VisionEnums.GROQ_QWEN.value):
                api_key = getattr(self.config, "GROQ_API_KEY", None)
                if not api_key:
                    return NullVisionProvider(reason="GROQ_API_KEY missing")
                from .providers import GroqProvider
                client = GroqProvider(api_key=api_key, model_id=model_id, **common)

            else:  # pragma: no cover - guarded above
                return NullVisionProvider(reason=f"unhandled provider '{provider}'")

        except ImportError as e:
            logger.warning(
                "Vision SDK for provider '%s' not installed (%s). Using NullVisionProvider.",
                provider, e,
            )
            return NullVisionProvider(reason=f"SDK import failed for {provider}")
        except Exception as e:  # noqa: BLE001 - never let construction break startup
            logger.warning(
                "Failed to construct vision provider '%s' (%s). Using NullVisionProvider.",
                provider, e,
            )
            return NullVisionProvider(reason=f"construction failed for {provider}")

        if not client.is_configured():
            logger.warning(
                "Vision provider '%s' constructed but reports not configured. Using NullVisionProvider.",
                provider,
            )
            return NullVisionProvider(reason=f"{provider} not configured")

        logger.info("Vision provider '%s' active (model=%s).", provider, model_id)
        return client
