from enum import Enum


class VisionEnums(Enum):
    """
    Selector values for the active vision provider.
    Consumed via the ``VISION_PROVIDER`` environment variable.
    """
    GEMINI = "GEMINI"
    MISTRAL = "MISTRAL"
    GROQ_LLAMA_SCOUT = "GROQ_LLAMA_SCOUT"
    GROQ_QWEN = "GROQ_QWEN"


class VisionModelEnums(Enum):
    """
    Default model identifiers per provider selector. These act as the
    baseline model IDs and can be overridden at runtime with the optional
    ``VISION_MODEL_ID`` setting.
    """
    GEMINI = "gemini-3.5-flash"
    MISTRAL = "mistral-ocr-latest"
    GROQ_LLAMA_SCOUT = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_QWEN = "qwen/qwen3.6-27b"


# Convenience mapping: provider selector -> default model id.
DEFAULT_VISION_MODELS: dict[str, str] = {
    VisionEnums.GEMINI.value: VisionModelEnums.GEMINI.value,
    VisionEnums.MISTRAL.value: VisionModelEnums.MISTRAL.value,
    VisionEnums.GROQ_LLAMA_SCOUT.value: VisionModelEnums.GROQ_LLAMA_SCOUT.value,
    VisionEnums.GROQ_QWEN.value: VisionModelEnums.GROQ_QWEN.value,
}


class VisionContentType(Enum):
    """Content-type tags used in PDF element metadata."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    PAGE_SCAN = "page_scan"
