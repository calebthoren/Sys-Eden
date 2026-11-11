"""One non-secret settings view for direct and interactive clients."""

from sys_eden.config import Settings


def settings_view(settings: Settings) -> dict[str, object]:
    return {
        "cli": settings.cli.model_dump(mode="json"),
        "storage": settings.storage.model_dump(mode="json"),
        "model": {
            "provider": settings.model.provider, "endpoint": settings.model.endpoint,
            "default_model": settings.model.default_model,
            "routing_preference": settings.model.routing_preference,
        },
    }
