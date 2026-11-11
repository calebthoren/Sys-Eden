"""Runtime-independent model contracts and deterministic test provider."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ModelCapability(StrEnum):
    TEXT = "text"
    STRUCTURED_OUTPUT = "structured_output"
    TOOLS = "tools"
    VISION = "vision"
    THINKING = "thinking"


class ModelSpeed(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    STRONG = "strong"


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    available: bool
    simulated: bool = False
    version: str | None = Field(default=None, max_length=200)
    endpoint: str | None = Field(default=None, max_length=2000)
    message: str | None = Field(default=None, max_length=500)


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=500)
    display_name: str = Field(min_length=1, max_length=500)
    provider: str = Field(min_length=1, max_length=100)
    local: bool = True
    context_window: int | None = Field(default=None, gt=0)
    capabilities: set[ModelCapability] = Field(default_factory=set)
    estimated_vram_bytes: int | None = Field(default=None, ge=0)
    estimated_ram_bytes: int | None = Field(default=None, ge=0)
    disk_size_bytes: int | None = Field(default=None, ge=0)
    disk_path: str | None = Field(default=None, max_length=4000)
    quantization: str | None = Field(default=None, max_length=100)
    parameter_size: str | None = Field(default=None, max_length=100)
    speed_class: ModelSpeed | None = None
    strength_class: ModelSpeed | None = None
    specializations: set[str] = Field(default_factory=set)
    loaded: bool = False
    modified_at: str | None = Field(default=None, max_length=200)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=500)
    prompt: str = Field(min_length=1, max_length=200_000)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    output_schema: dict[str, Any] | None = None
    think: bool = False
    temperature: float = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=2048, ge=1, le=32_768)
    keep_alive: str = Field(default="5m", min_length=1, max_length=100)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=500)
    text: str
    structured_data: dict[str, Any] | None = None
    done_reason: str | None = Field(default=None, max_length=100)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_duration_seconds: float | None = Field(default=None, ge=0)


class ModelErrorCode(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_NOT_FOUND = "model_not_found"
    REQUEST_FAILED = "request_failed"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    NO_SUITABLE_MODEL = "no_suitable_model"


class ModelProviderError(RuntimeError):
    """A stable error boundary that never requires parsing provider text."""

    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.provider = provider


class ModelUnavailable(ModelProviderError):
    def __init__(
        self,
        message: str = "The model provider is unavailable.",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(ModelErrorCode.PROVIDER_UNAVAILABLE, message, provider=provider)


class ModelNotFound(ModelProviderError):
    def __init__(
        self,
        message: str = "The selected model is not installed.",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(ModelErrorCode.MODEL_NOT_FOUND, message, provider=provider)


class ModelRequestFailed(ModelProviderError):
    def __init__(
        self,
        message: str = "The model request failed.",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(ModelErrorCode.REQUEST_FAILED, message, provider=provider)


class ModelTimedOut(ModelProviderError):
    def __init__(
        self,
        message: str = "The model request timed out.",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(ModelErrorCode.TIMEOUT, message, provider=provider)


class InvalidModelResponse(ModelProviderError):
    def __init__(
        self,
        message: str = "The model returned an invalid response.",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(ModelErrorCode.INVALID_RESPONSE, message, provider=provider)


class NoSuitableModel(ModelProviderError):
    def __init__(self, message: str = "No installed model satisfies the request.") -> None:
        super().__init__(ModelErrorCode.NO_SUITABLE_MODEL, message)


class ModelProvider(Protocol):
    async def health(self) -> ProviderHealth: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...


FakeResponder = Callable[[ModelRequest], ModelResponse]


class FakeModelProvider:
    """Deterministic provider for tests and development without a runtime."""

    def __init__(
        self,
        *,
        models: list[ModelInfo] | None = None,
        responder: FakeResponder | None = None,
        available: bool = True,
    ) -> None:
        self._available = available
        self._models = models or [
            ModelInfo(
                model_id="fake-diagnostic",
                display_name="Fake diagnostic model",
                provider="fake",
                context_window=32_768,
                capabilities={ModelCapability.TEXT, ModelCapability.STRUCTURED_OUTPUT},
                speed_class=ModelSpeed.FAST,
                strength_class=ModelSpeed.BALANCED,
                loaded=True,
            )
        ]
        self._responder = responder

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider="fake", available=self._available, simulated=True)

    async def list_models(self) -> list[ModelInfo]:
        if not self._available:
            raise ModelUnavailable(provider="fake")
        return list(self._models)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if not self._available:
            raise ModelUnavailable(provider="fake")
        if request.model_id not in {model.model_id for model in self._models}:
            raise ModelNotFound(provider="fake")
        if self._responder is not None:
            return self._responder(request)
        return ModelResponse(
            provider="fake",
            model_id=request.model_id,
            text="Fake model response.",
        )
