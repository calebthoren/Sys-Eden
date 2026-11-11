"""Local-only Ollama adapter behind the runtime-independent provider protocol."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sys_eden.models import (
    InvalidModelResponse,
    ModelCapability,
    ModelInfo,
    ModelNotFound,
    ModelRequest,
    ModelRequestFailed,
    ModelResponse,
    ModelSpeed,
    ModelTimedOut,
    ModelUnavailable,
    ProviderHealth,
)


class _OllamaDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameter_size: str | None = None
    quantization_level: str | None = None
    context_length: int | None = None


class _OllamaModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    model: str | None = None
    modified_at: str | None = None
    size: int | None = Field(default=None, ge=0)
    details: _OllamaDetails = Field(default_factory=_OllamaDetails)
    capabilities: list[str] = Field(default_factory=list)

    @property
    def identifier(self) -> str:
        return self.model or self.name or ""


class _OllamaTags(BaseModel):
    model_config = ConfigDict(extra="ignore")

    models: list[_OllamaModel] = Field(default_factory=list)


class _OllamaRunning(BaseModel):
    model_config = ConfigDict(extra="ignore")

    models: list[_OllamaModel] = Field(default_factory=list)


class _OllamaVersion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str


class _OllamaGeneration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    response: str
    done: bool = True
    done_reason: str | None = None
    total_duration: int | None = Field(default=None, ge=0)
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)


class OllamaProvider:
    """Async Ollama client that refuses remote and cloud model execution."""

    name = "ollama"

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434",
        *,
        health_timeout_seconds: float = 3,
        request_timeout_seconds: float = 180,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama provider endpoint must be loopback-only")
        self.endpoint = endpoint.rstrip("/")
        self.health_timeout_seconds = health_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.transport = transport

    def _client(self, timeout_seconds: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
            follow_redirects=False,
            transport=self.transport,
        )

    async def health(self) -> ProviderHealth:
        try:
            async with self._client(self.health_timeout_seconds) as client:
                response = await client.get("/api/version")
                response.raise_for_status()
                version = _OllamaVersion.model_validate(response.json()).version
        except (httpx.HTTPError, ValidationError, ValueError):
            return ProviderHealth(
                provider=self.name,
                available=False,
                endpoint=self.endpoint,
                message="Local Ollama runtime is not responding.",
            )
        return ProviderHealth(
            provider=self.name,
            available=True,
            version=version,
            endpoint=self.endpoint,
        )

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client(self.health_timeout_seconds) as client:
                tags_response = await client.get("/api/tags")
                tags_response.raise_for_status()
                tags = _OllamaTags.model_validate(tags_response.json())
                loaded_ids: set[str] = set()
                try:
                    running_response = await client.get("/api/ps")
                    running_response.raise_for_status()
                    running = _OllamaRunning.model_validate(running_response.json())
                    loaded_ids = {model.identifier for model in running.models}
                except (httpx.HTTPError, ValidationError, ValueError):
                    # Installed-model discovery remains useful when loaded-state discovery fails.
                    pass
        except httpx.TimeoutException as error:
            raise ModelTimedOut(provider=self.name) from error
        except httpx.HTTPError as error:
            raise ModelUnavailable(provider=self.name) from error
        except (ValidationError, ValueError) as error:
            raise InvalidModelResponse(provider=self.name) from error

        return [self._model_info(model, loaded_ids) for model in tags.models if model.identifier]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        installed = {model.model_id: model for model in await self.list_models()}
        selected = installed.get(request.model_id)
        if selected is None or not selected.local:
            raise ModelNotFound(
                "The selected local model is not installed.",
                provider=self.name,
            )

        body: dict[str, Any] = {
            "model": request.model_id,
            "prompt": request.prompt,
            "stream": False,
            "think": request.think,
            "keep_alive": request.keep_alive,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }
        if request.system_prompt:
            body["system"] = request.system_prompt
        if request.output_schema is not None:
            body["format"] = request.output_schema

        try:
            async with self._client(self.request_timeout_seconds) as client:
                response = await client.post("/api/generate", json=body)
                if response.status_code == 404:
                    raise ModelNotFound(provider=self.name)
                response.raise_for_status()
                generated = _OllamaGeneration.model_validate(response.json())
        except ModelNotFound:
            raise
        except httpx.TimeoutException as error:
            raise ModelTimedOut(provider=self.name) from error
        except httpx.HTTPError as error:
            raise ModelRequestFailed(provider=self.name) from error
        except (ValidationError, ValueError) as error:
            raise InvalidModelResponse(provider=self.name) from error

        structured: dict[str, Any] | None = None
        if request.output_schema is not None:
            try:
                parsed = json.loads(generated.response)
            except json.JSONDecodeError as error:
                raise InvalidModelResponse(
                    "The model did not return valid structured JSON.", provider=self.name
                ) from error
            if not isinstance(parsed, dict):
                raise InvalidModelResponse(
                    "The model's structured response was not an object.", provider=self.name
                )
            structured = parsed

        return ModelResponse(
            provider=self.name,
            model_id=generated.model,
            text=generated.response,
            structured_data=structured,
            done_reason=generated.done_reason,
            prompt_tokens=generated.prompt_eval_count,
            completion_tokens=generated.eval_count,
            total_duration_seconds=(
                generated.total_duration / 1_000_000_000
                if generated.total_duration is not None
                else None
            ),
        )

    def _model_info(self, model: _OllamaModel, loaded_ids: set[str]) -> ModelInfo:
        identifier = model.identifier
        local = bool(model.size) and not self._looks_cloud_managed(identifier)
        parameter_count = self._parameter_count_billions(model.details.parameter_size)
        capabilities = {ModelCapability.TEXT, ModelCapability.STRUCTURED_OUTPUT}
        for value in model.capabilities:
            normalized = value.casefold()
            if normalized in {item.value for item in ModelCapability}:
                capabilities.add(ModelCapability(normalized))
            elif normalized == "completion":
                capabilities.add(ModelCapability.TEXT)
        return ModelInfo(
            model_id=identifier,
            display_name=identifier,
            provider=self.name,
            local=local,
            context_window=model.details.context_length,
            capabilities=capabilities,
            disk_size_bytes=model.size,
            quantization=model.details.quantization_level,
            parameter_size=model.details.parameter_size,
            speed_class=self._speed_class(parameter_count),
            strength_class=self._strength_class(parameter_count),
            loaded=identifier in loaded_ids,
            modified_at=model.modified_at,
        )

    @staticmethod
    def _looks_cloud_managed(identifier: str) -> bool:
        normalized = identifier.casefold()
        return normalized.endswith((":cloud", "-cloud")) or "-cloud:" in normalized

    @staticmethod
    def _parameter_count_billions(value: str | None) -> float | None:
        if value is None:
            return None
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[Bb]", value)
        return float(match.group(1)) if match else None

    @staticmethod
    def _speed_class(parameters: float | None) -> ModelSpeed | None:
        if parameters is None:
            return None
        if parameters <= 4:
            return ModelSpeed.FAST
        if parameters <= 14:
            return ModelSpeed.BALANCED
        return ModelSpeed.STRONG

    @staticmethod
    def _strength_class(parameters: float | None) -> ModelSpeed | None:
        if parameters is None:
            return None
        if parameters < 4:
            return ModelSpeed.FAST
        if parameters < 12:
            return ModelSpeed.BALANCED
        return ModelSpeed.STRONG
