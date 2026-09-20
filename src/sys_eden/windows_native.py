"""Small read-only Win32 API adapters used by Windows inspection providers."""

import ctypes
import sys
from ctypes import wintypes
from typing import Any
from uuid import UUID

from pydantic import JsonValue


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _Luid(ctypes.Structure):
    _fields_ = [("low_part", wintypes.DWORD), ("high_part", wintypes.LONG)]


class _DxgiAdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("description", ctypes.c_wchar * 128),
        ("vendor_id", wintypes.UINT),
        ("device_id", wintypes.UINT),
        ("subsystem_id", wintypes.UINT),
        ("revision", wintypes.UINT),
        ("dedicated_video_memory", ctypes.c_size_t),
        ("dedicated_system_memory", ctypes.c_size_t),
        ("shared_system_memory", ctypes.c_size_t),
        ("adapter_luid", _Luid),
        ("flags", wintypes.UINT),
    ]


class _WlanInterfaceInfo(ctypes.Structure):
    _fields_ = [
        ("interface_guid", _Guid),
        ("description", ctypes.c_wchar * 256),
        ("state", wintypes.DWORD),
    ]


class _WlanRealtimeConnectionQuality(ctypes.Structure):
    _fields_ = [
        ("phy_type", wintypes.DWORD),
        ("link_quality", wintypes.DWORD),
        ("receive_rate_kbps", wintypes.DWORD),
        ("transmit_rate_kbps", wintypes.DWORD),
        ("is_mlo_connection", wintypes.BOOL),
        ("link_count", wintypes.DWORD),
    ]


def _guid(value: str) -> _Guid:
    parsed = UUID(value)
    return _Guid(
        parsed.time_low,
        parsed.time_mid,
        parsed.time_hi_version,
        (ctypes.c_ubyte * 8)(*parsed.bytes[8:]),
    )


def _com_method(
    pointer: ctypes.c_void_p,
    index: int,
    result_type: Any,
    *argument_types: Any,
) -> Any:
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)
    return prototype(table[index])


def _release(pointer: ctypes.c_void_p) -> None:
    _com_method(pointer, 2, wintypes.ULONG)(pointer)


def _failed(result: int) -> bool:
    return result < 0


def query_dxgi_adapters() -> list[dict[str, JsonValue]]:
    """Return DXGI 1.1 adapter identity and memory capacity without telemetry."""
    if sys.platform != "win32":
        raise OSError("DXGI is available only on Windows")

    dxgi = ctypes.WinDLL("dxgi.dll")
    create_factory = dxgi.CreateDXGIFactory1
    create_factory.argtypes = [ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    create_factory.restype = wintypes.LONG

    factory = ctypes.c_void_p()
    interface_id = _guid("770aae78-f26f-4dba-a829-253c83d1b387")
    result = create_factory(ctypes.byref(interface_id), ctypes.byref(factory))
    if _failed(result) or not factory.value:
        raise OSError(f"CreateDXGIFactory1 failed: 0x{result & 0xFFFFFFFF:08X}")

    rows: list[dict[str, JsonValue]] = []
    try:
        enum_adapters = _com_method(
            factory,
            12,
            wintypes.LONG,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
        )
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            result = enum_adapters(factory, index, ctypes.byref(adapter))
            if result & 0xFFFFFFFF == 0x887A0002:  # DXGI_ERROR_NOT_FOUND
                break
            if _failed(result) or not adapter.value:
                raise OSError(
                    f"IDXGIFactory1::EnumAdapters1 failed: 0x{result & 0xFFFFFFFF:08X}"
                )
            try:
                description = _DxgiAdapterDesc1()
                get_description = _com_method(
                    adapter,
                    10,
                    wintypes.LONG,
                    ctypes.POINTER(_DxgiAdapterDesc1),
                )
                result = get_description(adapter, ctypes.byref(description))
                if _failed(result):
                    raise OSError(
                        f"IDXGIAdapter1::GetDesc1 failed: 0x{result & 0xFFFFFFFF:08X}"
                    )
                luid = (
                    (int(description.adapter_luid.high_part) & 0xFFFFFFFF) << 32
                ) | int(description.adapter_luid.low_part)
                rows.append(
                    {
                        "Name": description.description.rstrip("\x00"),
                        "VendorId": int(description.vendor_id),
                        "DeviceId": int(description.device_id),
                        "SubsystemId": int(description.subsystem_id),
                        "Revision": int(description.revision),
                        "DedicatedVideoMemory": int(description.dedicated_video_memory),
                        "DedicatedSystemMemory": int(description.dedicated_system_memory),
                        "SharedSystemMemory": int(description.shared_system_memory),
                        "AdapterLuid": f"{luid:016X}",
                        "Flags": int(description.flags),
                    }
                )
            finally:
                _release(adapter)
            index += 1
    finally:
        _release(factory)
    return rows


def query_wifi_quality() -> list[dict[str, JsonValue]]:
    """Return location-independent Native Wi-Fi connection quality."""
    if sys.platform != "win32":
        raise OSError("Native Wi-Fi is available only on Windows")

    wlan = ctypes.WinDLL("wlanapi.dll")
    open_handle = wlan.WlanOpenHandle
    open_handle.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.HANDLE),
    ]
    open_handle.restype = wintypes.DWORD
    enum_interfaces = wlan.WlanEnumInterfaces
    enum_interfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    enum_interfaces.restype = wintypes.DWORD
    query_interface = wlan.WlanQueryInterface
    query_interface.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_Guid),
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    query_interface.restype = wintypes.DWORD
    free_memory = wlan.WlanFreeMemory
    free_memory.argtypes = [ctypes.c_void_p]
    close_handle = wlan.WlanCloseHandle
    close_handle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    close_handle.restype = wintypes.DWORD

    negotiated_version = wintypes.DWORD()
    handle = wintypes.HANDLE()
    result = open_handle(2, None, ctypes.byref(negotiated_version), ctypes.byref(handle))
    if result != 0:
        raise ctypes.WinError(result)

    rows: list[dict[str, JsonValue]] = []
    query_errors: list[int] = []
    interfaces = ctypes.c_void_p()
    try:
        result = enum_interfaces(handle, None, ctypes.byref(interfaces))
        if result != 0:
            raise ctypes.WinError(result)
        count = ctypes.cast(interfaces, ctypes.POINTER(wintypes.DWORD)).contents.value
        first_address = int(interfaces.value or 0) + (2 * ctypes.sizeof(wintypes.DWORD))
        interface_array = ctypes.cast(
            first_address,
            ctypes.POINTER(_WlanInterfaceInfo * count),
        ).contents
        for interface in interface_array:
            data_size = wintypes.DWORD()
            data = ctypes.c_void_p()
            opcode_type = wintypes.DWORD()
            # wlan_intf_opcode_realtime_connection_quality
            result = query_interface(
                handle,
                ctypes.byref(interface.interface_guid),
                19,
                None,
                ctypes.byref(data_size),
                ctypes.byref(data),
                ctypes.byref(opcode_type),
            )
            if result == 5:
                raise PermissionError("Native Wi-Fi quality access denied")
            if result != 0:
                # ERROR_INVALID_STATE is expected for disconnected interfaces.
                if result != 5023:
                    query_errors.append(result)
                continue
            if not data.value:
                continue
            try:
                if data_size.value < ctypes.sizeof(_WlanRealtimeConnectionQuality):
                    continue
                quality = ctypes.cast(
                    data, ctypes.POINTER(_WlanRealtimeConnectionQuality)
                ).contents
                guid_bytes = ctypes.string_at(
                    ctypes.byref(interface.interface_guid), ctypes.sizeof(_Guid)
                )
                rows.append(
                    {
                        "InterfaceGuid": "{" + str(UUID(bytes_le=guid_bytes)).upper() + "}",
                        "InterfaceDescription": interface.description.rstrip("\x00"),
                        "SignalQuality": int(quality.link_quality),
                        "ReceiveRateKbps": int(quality.receive_rate_kbps),
                        "TransmitRateKbps": int(quality.transmit_rate_kbps),
                        "PhyType": int(quality.phy_type),
                        "IsMloConnection": bool(quality.is_mlo_connection),
                        "LinkCount": int(quality.link_count),
                    }
                )
            finally:
                free_memory(data)
    finally:
        if interfaces.value:
            free_memory(interfaces)
        close_handle(handle, None)
    if not rows and query_errors:
        raise ctypes.WinError(query_errors[0])
    return rows
