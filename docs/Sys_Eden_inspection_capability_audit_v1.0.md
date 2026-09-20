# Sys Eden — Read-Only Inspection Capability Audit

> **Document role:** Milestone 2 implementation audit  
> **Status:** Completed on 2026-09-19  
> **Scope:** Dedicated GPU memory, storage health and configuration, service dependencies, and live network information  
> **Execution context:** Logged-in user; Eden Core was not elevated

## Purpose and method

This audit separates fields that are absent from a provider, fields that need a
different documented Windows or vendor provider, and fields denied to the current
user. Probes were read-only. They did not change location consent, storage
configuration, security settings, or host software.

The result classifications used below are:

- **Direct:** the provider reports the value or configuration itself.
- **Derived:** Eden calculates the value from direct observations.
- **Unavailable:** no suitable value was returned in the permitted context.

Live-result descriptions intentionally omit serial numbers, MAC addresses, IP
addresses, SSIDs, and other machine-specific identifiers.

## Capability matrix

| Field | Current source and reason for prior unavailability | Documented alternative | Administrator required | Result on this machine | Decision | Result type |
|---|---|---|---|---|---|---|
| Dedicated GPU VRAM capacity | `Win32_VideoController.AdapterRAM` is an unsigned 32-bit byte count and cannot represent modern capacities above about 4 GiB. Eden previously rejected it rather than showing a truncated value. | DXGI `IDXGIAdapter1::GetDesc1` / `DXGI_ADAPTER_DESC1.DedicatedVideoMemory`; installed NVIDIA drivers also provide `nvidia-smi --query-gpu=memory.total`. | No | DXGI returned dedicated-memory values for the hardware adapters. NVIDIA SMI returned about 12 GiB for the discrete NVIDIA adapter. | Implemented. NVIDIA's vendor inventory overrides DXGI capacity for a name-matched NVIDIA adapter; DXGI is the general fallback. The source is preserved. | Direct inventory |
| Shared GPU memory limit and stable adapter match | Generic video CIM does not expose the DXGI shared-memory limit or adapter LUID. | `DXGI_ADAPTER_DESC1.SharedSystemMemory` and `AdapterLuid`. | No | Returned for hardware adapters. | Implemented in detailed output as useful provider/matching context. | Direct inventory |
| GPU utilization, temperature, clocks, VRAM use, and power | `Win32_VideoController` does not provide reliable current telemetry for these fields. | Windows GPU performance counters and vendor APIs/tools such as NVIDIA NVML/SMI; vendor coverage differs. | Usually no, but provider- and counter-specific access varies. | A vendor tool is present for the NVIDIA device, but complete cross-vendor semantics were not established by this focused audit. | Deferred. This would become a GPU telemetry subsystem and belongs to a later milestone. | Unavailable in current inspection |
| Storage health and operational status | `MSFT_PhysicalDisk` already returns its high-level `HealthStatus` and `OperationalStatus`. | Windows Storage Management provider. | No on this machine | Returned `Healthy` / `OK`. | Retained in normal output. | Direct status |
| Drive temperature, read/write errors, wear, and power-on hours | The base physical-disk class does not contain these counters. | `Get-StorageReliabilityCounter` / `MSFT_StorageReliabilityCounter`. | The normal-user query was denied on this machine; use the future narrow privileged System Service where needed. | Access denied. No values returned. | Provider interface and typed fields are preserved; collection is deferred to the System Service. | Unavailable due to permission |
| Volume encryption state, protection, and method | `MSFT_Volume` does not provide BitLocker state. | `Win32_EncryptableVolume` or `Get-BitLockerVolume`. | Yes for the documented BitLocker provider operations used here. | Both normal-user probes were denied. | Provider interface and typed fields are preserved; collection is deferred to the System Service. | Unavailable due to permission |
| Filesystem delete notifications (TRIM/unmap configuration) | No earlier provider was wired. | Read-only `fsutil behavior query DisableDeleteNotify`. A value of zero means delete notifications are enabled for that filesystem. | No for this query on this machine | NTFS and ReFS both reported delete notifications enabled. | Implemented in detailed output. It is labeled filesystem configuration and is not presented as proof that a particular device accepts or executes TRIM. | Direct configuration |
| Per-device TRIM support and actual TRIM execution | The filesystem setting cannot prove device capability or command execution. | Storage protocol/device queries and optimization analysis can add evidence, but require careful device mapping and may need elevated access. | Provider-dependent; likely elevated for the useful low-level paths. | Not tested beyond the safe filesystem configuration query. | Deferred. The existing per-device field stays unavailable. | Unavailable |
| Service dependencies and dependent services | `Win32_Service` does not include relationship lists. | `Win32_DependentService` association instances. | No | Returned dependency relationships for installed services. | Implemented in detailed service output, including both directions. | Direct configuration |
| Adapter receive/send throughput | Static CIM adapter/configuration rows do not expose a meaningful instantaneous rate. | Sample cumulative byte counters from `Get-NetAdapterStatistics` twice and divide the delta by elapsed monotonic time. | No | Returned counters for Ethernet and Wi-Fi; a short sample produced rates for active adapters. | Implemented in normal output with the sample duration in details. Counter resets clamp the rate to zero. | Derived measurement |
| Adapter error and discard counters | The prior generic adapter query did not request statistics. | `Get-NetAdapterStatistics` / `MSFT_NetAdapterStatisticsSettingData`. | No | Returned cumulative error/discard counters. | Implemented in detailed output. | Direct cumulative counters |
| Wi-Fi signal quality and receive/transmit link rates | Generic adapter CIM does not expose the connected radio quality. | Native Wi-Fi `WlanQueryInterface` with `wlan_intf_opcode_realtime_connection_quality`, which Microsoft documents as location-independent. | No | Returned signal quality and both link rates for the connected Wi-Fi interface. | Implemented. Interface GUID or hardware description correlates the result without exposing the SSID. | Direct measurement |
| Connected Wi-Fi SSID | Generic adapter CIM does not expose SSID. Native Wi-Fi current-connection data is location-sensitive on current Windows releases. | `WlanQueryInterface` with `wlan_intf_opcode_current_connection`, or tools that use it, after the user grants Windows location consent. | Administrator rights alone are not the privacy grant; location consent is required. | The host denied the query because location access is disabled. | Deferred. Eden does not change location settings or bypass consent. The field remains unavailable. | Unavailable due to privacy permission |
| Public/external IP | A local provider cannot determine this reliably; an external lookup would disclose network data. | Purpose-limited external service lookup. | No | Not attempted. | Intentionally excluded from basic local inspection. | Unavailable by design |

## Provider boundaries retained for later work

The collector depends on small protocols for GPU inventory, storage reliability,
volume encryption, service dependencies, adapter statistics, Wi-Fi quality, and
filesystem delete-notification configuration. The normal-user Windows reader is
wired only to providers that succeeded without changing host permissions. The
reliability and encryption protocols can later be implemented by the planned
System Service without changing inspection result models or moving privileged
authority into Core.

The implementation adds no general command execution surface. PowerShell scripts
remain fixed and read-only; DXGI and Native Wi-Fi calls are narrow native adapters;
and NVIDIA SMI is invoked only from its trusted System32 location with a fixed
inventory query.

## References

- [Win32_VideoController](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-videocontroller)
- [DXGI_ADAPTER_DESC1](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/ns-dxgi-dxgi_adapter_desc1)
- [NVIDIA System Management Interface](https://docs.nvidia.com/deploy/nvidia-smi/)
- [Get-StorageReliabilityCounter](https://learn.microsoft.com/en-us/powershell/module/storage/get-storagereliabilitycounter)
- [MSFT_StorageReliabilityCounter](https://learn.microsoft.com/en-us/windows-hardware/drivers/storage/msft-storagereliabilitycounter)
- [Win32_EncryptableVolume](https://learn.microsoft.com/en-us/windows/win32/secprov/win32-encryptablevolume)
- [fsutil behavior](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-behavior)
- [Win32_DependentService](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-dependentservice)
- [Get-NetAdapterStatistics](https://learn.microsoft.com/en-us/powershell/module/netadapter/get-netadapterstatistics)
- [Windows Wi-Fi access and location changes](https://learn.microsoft.com/en-us/windows/win32/nativewifi/wi-fi-access-location-changes)
- [WLAN_INTF_OPCODE](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/ne-wlanapi-wlan_intf_opcode)
- [WLAN_REALTIME_CONNECTION_QUALITY](https://learn.microsoft.com/en-us/windows/win32/api/wlanapi/ns-wlanapi-wlan_realtime_connection_quality)
