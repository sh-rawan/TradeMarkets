"""Cap how much physical RAM this process may hold (Windows only).

Uses a hard working-set maximum: pages beyond the cap are moved to the page file instead of
failing, so a run that needs more is slower rather than crashing. GPU memory is not affected.
"""
import ctypes
import sys
from ctypes import wintypes

QUOTA_LIMITS_HARDWS_MIN_DISABLE = 0x2
QUOTA_LIMITS_HARDWS_MAX_ENABLE = 0x4
MIN_WORKING_SET = 64 * 2**20


def limit_ram(gb):
    if sys.platform != "win32" or not gb:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetProcessWorkingSetSizeEx.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t,
                                                    wintypes.DWORD]
    ok = kernel32.SetProcessWorkingSetSizeEx(
        kernel32.GetCurrentProcess(), MIN_WORKING_SET, int(gb * 2**30),
        QUOTA_LIMITS_HARDWS_MIN_DISABLE | QUOTA_LIMITS_HARDWS_MAX_ENABLE)
    if not ok:
        print(f"Could not cap RAM at {gb} GB (error {ctypes.get_last_error()})")
    return bool(ok)
