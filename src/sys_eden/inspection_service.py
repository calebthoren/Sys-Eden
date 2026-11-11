"""Core-owned read-only inspection application service."""

from __future__ import annotations

from sys_eden.inspection import InspectionProvider, InspectionResult, collect
from sys_eden.windows import WindowsCimReader
from sys_eden.windows_collectors import WindowsInspectionProvider

SUPPORTED_INSPECTION_COMPONENTS = (
    "system",
    "cpu",
    "ram",
    "gpu",
    "storage",
    "network",
    "processes",
    "services",
    "startup",
    "drivers",
    "software",
    "events",
    "crashes",
    "boot",
)


def create_windows_inspection_provider() -> WindowsInspectionProvider:
    reader = WindowsCimReader()
    return WindowsInspectionProvider(
        reader,
        software_reader=reader,
        event_reader=reader,
        graphics_reader=reader,
        service_dependency_reader=reader,
        network_statistics_reader=reader,
        wifi_quality_reader=reader,
        storage_trim_reader=reader,
    )


class InspectionService:
    def __init__(self, provider: InspectionProvider):
        self.provider = provider

    @staticmethod
    def normalize_component(component: str) -> str:
        normalized = "system" if component == "os" else component
        if normalized != "all" and normalized not in SUPPORTED_INSPECTION_COMPONENTS:
            raise ValueError(
                "Supported components: all, "
                + ", ".join(SUPPORTED_INSPECTION_COMPONENTS)
            )
        return normalized

    async def inspect(self, component: str, *, details: bool = False) -> list[InspectionResult]:
        normalized = self.normalize_component(component)
        names = (
            SUPPORTED_INSPECTION_COMPONENTS if normalized == "all" else (normalized,)
        )
        return [await collect(name, self.provider, details=details) for name in names]
