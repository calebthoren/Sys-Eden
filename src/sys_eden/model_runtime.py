"""Configuration-driven construction of replaceable model providers."""

from sys_eden.config import Settings
from sys_eden.models import FakeModelProvider, ModelProvider
from sys_eden.ollama import OllamaProvider


def create_model_provider(settings: Settings) -> ModelProvider:
    if settings.model.provider == "fake":
        return FakeModelProvider()
    return OllamaProvider(
        settings.model.endpoint,
        health_timeout_seconds=settings.model.health_timeout_seconds,
        request_timeout_seconds=settings.model.request_timeout_seconds,
    )
