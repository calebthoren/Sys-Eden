"""Small deterministic model router for the first local-model milestone."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from sys_eden.models import ModelCapability, ModelInfo, ModelSpeed, NoSuitableModel


class RoutingPreference(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    STRONG = "strong"


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_capabilities: set[ModelCapability] = Field(default_factory=set)
    required_context_characters: int = Field(default=0, ge=0)
    preferred_model: str | None = Field(default=None, max_length=500)
    preference: RoutingPreference = RoutingPreference.BALANCED


class ModelRouter:
    """Selects only installed local models with the requested capabilities."""

    def select(self, models: list[ModelInfo], request: ModelSelection) -> ModelInfo:
        eligible = [model for model in models if self._eligible(model, request)]
        if not eligible:
            raise NoSuitableModel()

        if request.preferred_model is not None:
            preferred = next(
                (model for model in eligible if model.model_id == request.preferred_model), None
            )
            if preferred is not None:
                return preferred

        target = ModelSpeed(request.preference.value)
        return min(
            eligible,
            key=lambda model: (
                self._class_distance(model, target),
                -(model.context_window or 0),
                model.disk_size_bytes or 0,
                model.model_id,
            ),
        )

    @staticmethod
    def _eligible(model: ModelInfo, request: ModelSelection) -> bool:
        if not model.local or not request.required_capabilities.issubset(model.capabilities):
            return False
        if model.context_window is None:
            return True
        # Four characters per token is a conservative routing estimate, not a tokenizer claim.
        return model.context_window * 4 >= request.required_context_characters

    @staticmethod
    def _class_distance(model: ModelInfo, target: ModelSpeed) -> int:
        classes = [ModelSpeed.FAST, ModelSpeed.BALANCED, ModelSpeed.STRONG]
        actual = model.strength_class or model.speed_class or ModelSpeed.BALANCED
        return abs(classes.index(actual) - classes.index(target))
