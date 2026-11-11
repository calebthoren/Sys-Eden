"""Human storage views shared by the CLI clients."""

from sys_eden.storage_status import StorageStatus


def size_label(value: int) -> str:
    if abs(value) >= 1024**3:
        return f"{value / 1024**3:.2f} GiB"
    if abs(value) >= 1024**2:
        return f"{value / 1024**2:.2f} MiB"
    if abs(value) >= 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value} bytes"


def render_storage_status(status: StorageStatus, *, details: bool) -> str:
    lines = [
        f"Storage pressure: {status.pressure.value.replace('_', ' ')}",
        f"Reports, memory and database budget: {size_label(status.shared_budget_bytes)}",
        f"Budget remaining: {size_label(status.shared_budget_remaining_bytes)}",
        f"Database + WAL: {size_label(status.database_file_bytes + status.wal_file_bytes)}",
        f"Host free space: {size_label(status.host_free_bytes)}",
        f"Protected free-space reserve: {size_label(status.protected_free_space_reserve_bytes)}",
    ]
    if details:
        lines.extend(["", "Estimated storage attribution"])
        for key, value in status.attribution.model_dump().items():
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {size_label(value)}")
        lines.extend(["", "Stored records and links"])
        for key, value in status.counts.model_dump().items():
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {value}")
        lines.extend(["", "Largest consumers"])
        lines.extend(f"  {item.object_id}: {size_label(item.estimated_bytes)}"
                     + (" (protected)" if item.protected else "")
                     for item in status.largest_consumers)
        lines.extend(["", *status.notes])
    return "\n".join(lines)
