"""Provider boundary for the scaffold's explicitly fake local model."""

from typing import Protocol

from pydantic import BaseModel


class ProviderHealth(BaseModel):
    provider: str
    available: bool
    simulated: bool = False


class ModelProvider(Protocol):
    async def health(self) -> ProviderHealth: ...


class FakeModelProvider:
    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider="fake", available=True, simulated=True)
