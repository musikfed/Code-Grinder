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
def guard_windows_parents(root: Path, target: Path, *, create: bool = False) -> Iterator[int | None]:
    """Pin the root and each ancestor using non-reparse Win32 directory handles."""
    if os.name != "nt":
        yield None
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
    FILE_ADD_FILE = 0x2
    FILE_TRAVERSE = 0x20
    FILE_SHARE_READ_WRITE = 0x1 | 0x2  # Exclude FILE_SHARE_DELETE to pin ancestors.
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def pin(directory: Path) -> tuple[int, str]:
        """Open a directory, rejecting any reparse-point and obtaining its real location."""
        handle = create_file(
            str(directory), FILE_READ_ATTRIBUTES | FILE_ADD_FILE | FILE_TRAVERSE,
            FILE_SHARE_READ_WRITE, None,
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
        yield handle if rel.parts[:-1] else root_handle


def replace_windows_staged(source: Path, destination_name: str, destination_parent: int) -> None:
    """Rename an opened source HANDLE relative to the pinned destination directory.

    Unlike os.replace(path, path), FILE_RENAME_INFO.RootDirectory prevents
    redirection of the destination through a swapped textual ancestor path.
    The operation is atomic for the destination leaf on NTFS, not across batches.
    """
    if os.name != "nt":
        raise RuntimeError("Native Windows replacement only works on Windows")
    if not destination_name or any(c in destination_name for c in ("/", "\\", "\x00")):
        raise ValueError("Destination must be one simple filename")

    import ctypes
    from ctypes import wintypes

    class FileRenameInfo(ctypes.Structure):
        """Win32 FILE_RENAME_INFO with a flexible UTF-16 filename."""

        _fields_ = [
            ("replace", wintypes.BOOLEAN),
            ("root", wintypes.HANDLE),
            ("length", wintypes.DWORD),
            ("filename", wintypes.WCHAR * 1),
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
    set_info = kernel32.SetFileInformationByHandle
    set_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_info.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    handle = create_file(
        str(source), 0x10000 | 0x80, 0x1 | 0x2 | 0x4, None,
        3, 0x200000, None,  # DELETE|FILE_READ_ATTRIBUTES; OPEN_REPARSE_POINT
    )
    if handle in (None, invalid):
        raise OSError(ctypes.get_last_error(), f"Cannot open staged file: {source}")
    try:
        utf16 = destination_name.encode("utf-16-le")
        size = ctypes.sizeof(FileRenameInfo) + len(utf16) + 2
        buffer = ctypes.create_string_buffer(size)
        info = FileRenameInfo.from_buffer(buffer)
        info.replace = True
        info.root = destination_parent
        info.length = len(utf16)
        ctypes.memmove(ctypes.addressof(info) + FileRenameInfo.filename.offset,
                       utf16, len(utf16))
        if not set_info(handle, 3, buffer, size):  # FileRenameInfo = 3
            raise OSError(ctypes.get_last_error(), "SetFileInformationByHandle failed")
    finally:
        close_handle(handle)
