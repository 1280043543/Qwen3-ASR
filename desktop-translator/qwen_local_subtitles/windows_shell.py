"""Associate the desktop shortcuts and Python-hosted app with one taskbar identity."""
from __future__ import annotations

import ctypes as c
from pathlib import Path
import sys
from uuid import UUID

APP_ID = "Qwen.LocalSubtitles.Desktop"
_GUID = c.c_ubyte * 16


class _PropertyKey(c.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", c.c_ulong)]


class _Value(c.Union):
    _fields_ = [("text", c.c_wchar_p), ("storage", c.c_void_p * 2)]


class _PropVariant(c.Structure):
    _fields_ = [("vt", c.c_ushort), ("reserved", c.c_ushort * 3), ("value", _Value)]


def set_process_app_id() -> None:
    if sys.platform == "win32":
        function = c.OleDLL("shell32").SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [c.c_wchar_p]
        function(APP_ID)


def set_shortcut_app_id(path: Path) -> None:
    """Write PKEY_AppUserModel_ID into a saved .lnk through IPropertyStore."""
    shell = c.OleDLL("shell32")
    ole = c.OleDLL("ole32")
    ole.CoInitialize.argtypes = [c.c_void_p]
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    initialized = False
    try:
        ole.CoInitialize(None)
        initialized = True
    except OSError as exc:
        if exc.winerror != -2147417850:  # RPC_E_CHANGED_MODE: reuse the existing COM apartment.
            raise
    store = c.c_void_p()
    try:
        iid = _GUID.from_buffer_copy(UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)
        get_store = shell.SHGetPropertyStoreFromParsingName
        get_store.argtypes = [c.c_wchar_p, c.c_void_p, c.c_ulong, c.POINTER(_GUID), c.POINTER(c.c_void_p)]
        get_store(str(Path(path).resolve()), None, 2, c.byref(iid), c.byref(store))  # GPS_READWRITE
        vtable = c.cast(store, c.POINTER(c.POINTER(c.c_void_p))).contents
        key = _PropertyKey(_GUID.from_buffer_copy(UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le), 5)
        value = _PropVariant()
        value.vt = 31  # VT_LPWSTR; ctypes keeps the string alive until SetValue copies it.
        value.value.text = APP_ID
        set_value = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.POINTER(_PropertyKey), c.POINTER(_PropVariant))(vtable[6])
        commit = c.WINFUNCTYPE(c.c_long, c.c_void_p)(vtable[7])
        result = set_value(store, c.byref(key), c.byref(value))
        if result >= 0:
            result = commit(store)
        if result < 0:
            raise OSError(f"Unable to save shortcut AppUserModelID: 0x{result & 0xffffffff:08x}")
    finally:
        if store.value:
            vtable = c.cast(store, c.POINTER(c.POINTER(c.c_void_p))).contents
            c.WINFUNCTYPE(c.c_ulong, c.c_void_p)(vtable[2])(store)  # Release
        if initialized:
            ole.CoUninitialize()
    notify = shell.SHChangeNotify
    notify.argtypes = [c.c_long, c.c_uint, c.c_void_p, c.c_void_p]
    notify.restype = None
    notify(0x2000, 0x5, c.c_wchar_p(str(Path(path).resolve())), None)  # UPDATEITEM, PATHW


if __name__ == "__main__":
    for shortcut in sys.argv[1:]:
        set_shortcut_app_id(Path(shortcut))

