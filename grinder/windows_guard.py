"""Windows parent-directory handle guard against junction and symlink swaps.

CreateFileW opens each ancestor with FILE_FLAG_OPEN_REPARSE_POINT and denies
FILE_SHARE_DELETE for the lifetime of the operation. This prevents an external
process from renaming/replacing an ancestor while os.replace executes.

This is not a full Windows security boundary for projects writable by hostile
users: leaf-file replacement races and ACL policies remain out of scope.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path


@contextmanager
def guard_windows_parents(root: Path, target: Path, *, create: bool = False) -> Iterator[None]:
    """Pin the root and each ancestor using non-reparse Win32 directory handles."""
    if os.name != "nt":
        yield
        return

    import ctypes
    from ctypes import wintypes

    class FileTime(ctypes.Structure):
        """Win32 FILETIME structure."""

        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class ByHandleInfo(ctypes.Structure):
        """Win32 BY_HANDLE_FILE_INFORMATION used to detect reparse points."""

        _fields_ = [
            ("attributes", wintypes.DWORD), ("creation", FileTime),
            ("access", FileTime), ("write", FileTime), ("serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD), ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD), ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_info = kernel32.GetFileInformationByHandle
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ByHandleInfo)]
    get_info.restype = wintypes.BOOL
    get_final = kernel32.GetFinalPathNameByHandleW
    get_final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final.restype = wintypes.DWORD

    FILE_READ_ATTRIBUTES = 0x80
    FILE_SHARE_READ_WRITE = 0x1 | 0x2  # Exclude FILE_SHARE_DELETE to pin ancestors.
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def pin(directory: Path) -> tuple[int, str]:
        """Open a directory, rejecting any reparse-point and obtaining its real location."""
        handle = create_file(
            str(directory), FILE_READ_ATTRIBUTES, FILE_SHARE_READ_WRITE, None,
            OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle in (None, INVALID_HANDLE_VALUE):
            raise OSError(ctypes.get_last_error(), f"Cannot pin directory: {directory}")
        try:
            info = ByHandleInfo()
            if not get_info(handle, ctypes.byref(info)):
                raise OSError(ctypes.get_last_error(), f"Cannot inspect directory: {directory}")
            if info.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError(f"Reparse point forbidden: {directory}")
            buffer = ctypes.create_unicode_buffer(32768)
            count = get_final(handle, buffer, len(buffer), 0)
            if count == 0 or count >= len(buffer):
                raise OSError(ctypes.get_last_error(), "GetFinalPathNameByHandleW failed")
            return handle, os.path.normcase(buffer.value.rstrip("\\"))
        except BaseException:
            close_handle(handle)
            raise

    with ExitStack() as stack:
        try:
            rel = target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Target is outside pinned root") from exc
        root_handle, root_real = pin(root)
        stack.callback(close_handle, root_handle)
        current = root
        for name in rel.parts[:-1]:
            current = current / name
            if create:
                try:
                    current.mkdir(mode=0o700)
                except FileExistsError:
                    pass
            handle, resolved = pin(current)
            stack.callback(close_handle, handle)
            if not (resolved == root_real or resolved.startswith(root_real + "\\")):
                raise RuntimeError("Directory handle escaped project root")
        yield
