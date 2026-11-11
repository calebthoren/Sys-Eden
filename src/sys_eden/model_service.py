"""Core-owned model catalog and structured diagnostic application service."""

from __future__ import annotations

from typing import Any

from sys_eden.config import ModelSettings
from sys_eden.diagnostics import DiagnosticProgress, DiagnosticResult, DiagnosticService
from sys_eden.inspection_service import InspectionService
from sys_eden.model_context import ContextBuilder
from sys_eden.model_routing import RoutingPreference
from sys_eden.models import ModelInfo, ModelProvider, ProviderHealth
from sys_eden.task_models import TechnicalOperation


class ModelService:
    def __init__(
        self,
        provider: ModelProvider,
        inspection: InspectionService,
        settings: ModelSettings,
    ) -> None:
        self.provider = provider
        self.inspection = inspection
        self.diagnostics = DiagnosticService(
            provider,
            context_builder=ContextBuilder(settings.context_max_characters),
            preferred_model=settings.default_model,
            routing_preference=RoutingPreference(settings.routing_preference),
            max_output_tokens=settings.max_output_tokens,
        )

    async def health(self) -> ProviderHealth:
        return await self.provider.health()

    async def list_models(self) -> list[ModelInfo]:
        return await self.provider.list_models()

    async def assess(
        self,
        *,
        concern: str,
        component: str = "system",
        snapshot: Any | None = None,
        historical_capsules: list[dict[str, Any]] | None = None,
        progress: DiagnosticProgress | None = None,
    ) -> DiagnosticResult:
        evidence = snapshot
        if evidence is None:
            if progress is not None:
                await progress(
                    "collecting_evidence", f"Collecting read-only {component} evidence.",
                    TechnicalOperation(
                        kind="inspection", provider="windows", tool="InspectionService.inspect",
                        workload_key=component,
                        summary=f"Collect current-user {component} evidence without mutation.",
                    ),
                )
            collected = await self.inspection.inspect(component)
            if any(not item.success for item in collected):
                raise ValueError("inspection failed; no model request was sent")
            evidence = [item.model_dump(mode="json") for item in collected]
        return await self.diagnostics.assess(
            concern=concern,
            snapshot=evidence,
            historical_capsules=historical_capsules,
            progress=progress,
        )
