"""Live recursive size metadata, never source-file contents or snapshot blocks."""

import hashlib
import os
import stat
import time

from . import bash, diagnostics
from .contracts import FileRecord, PolicyError


def verification(root_fd: int, relative: str) -> str:
    try:
        with bash._directory(root_fd, relative) as fd:
            fields = (bash._identity(os.fstat(root_fd)), bash._identity(os.fstat(fd)))
    except OSError:
        raise PolicyError("Size folder is unavailable, linked or unsafe; nothing scanned.") from None
    return hashlib.sha256(repr(fields).encode()).hexdigest()


def human_bytes(value: int) -> str:
    for power, unit in enumerate(("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")):
        if value < 1024 ** (power + 1) or unit == "EiB":
            return f"{value} B" if power == 0 else f"{value / 1024 ** power:.1f} {unit}"
    raise AssertionError("Unreachable size unit")


def usage(root_fd: int, relative: str, config, *, depth: int = 1, limit: int = 20,
          file_limit: int = 0) -> dict:
    """Account stat sizes/blocks in one approved mount, with explicit coverage.

    O_PATH pins file metadata without opening contents or waiting on a FIFO.
    Mount IDs also exclude same-device bind mounts. Hardlinked files are skipped,
    as in the Bash content policy, rather than exposing outside-linked metadata.
    This is an interval observation, not an atomic filesystem snapshot; deadlines
    apply between metadata syscalls, not to a blocked kernel filesystem operation.
    """
    records: list[FileRecord] = []
    allocated_directories: dict[str, int] = {}
    entries_seen = excluded = errors = 0
    truncated = False
    started = time.monotonic()
    deadline = started + config.usage_seconds
    with bash._directory(root_fd, relative) as target_fd:
        device, mount = os.fstat(target_fd).st_dev, bash._mount_id(target_fd)

        def walk(parent_fd: int, prefix: str, level: int) -> None:
            nonlocal entries_seen, excluded, errors, truncated
            metadata = os.fstat(parent_fd)
            allocated_directories[prefix or "."] = metadata.st_blocks * 512
            try:
                with os.scandir(parent_fd) as entries:
                    for entry in entries:
                        if entries_seen >= config.usage_entries or time.monotonic() >= deadline:
                            truncated = True
                            return
                        entries_seen += 1
                        if bash._protected(entry.name):
                            excluded += 1
                            continue
                        path = f"{prefix}/{entry.name}" if prefix else entry.name
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if info.st_dev != device or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                                excluded += 1
                                continue
                            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                                excluded += 1
                                continue
                            if stat.S_ISDIR(info.st_mode) and level >= config.usage_depth:
                                truncated = True
                                excluded += 1
                                continue
                            flags = (os.O_RDONLY | os.O_DIRECTORY if stat.S_ISDIR(info.st_mode) else os.O_PATH)
                            fd = os.open(entry.name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                            try:
                                current = os.fstat(fd)
                                if bash._mount_id(fd) != mount:
                                    excluded += 1
                                    continue
                                if bash._identity(current, content=True) != bash._identity(info, content=True):
                                    truncated = True
                                    errors += 1
                                    continue
                                if stat.S_ISREG(current.st_mode):
                                    records.append({"relative_path": path, "name": entry.name,
                                                    "size_bytes": current.st_size,
                                                    "allocated_size_bytes": current.st_blocks * 512})
                                else:
                                    walk(fd, path, level + 1)
                            finally:
                                os.close(fd)
                        except OSError:
                            errors += 1
                            truncated = True
                        if truncated and (entries_seen >= config.usage_entries or time.monotonic() >= deadline):
                            return
            except OSError:
                errors += 1
                truncated = True
        walk(target_fd, "", 0)
    data = diagnostics.collect_directory_usage(records, depth=depth, limit=limit, file_limit=file_limit,
                                               allocated_directories=allocated_directories)
    return {**data, "logical_size_human": human_bytes(data["total_size_bytes"]),
            "allocated_size_human": human_bytes(data["allocated_size_bytes"]),
            "scan_elapsed_seconds": round(time.monotonic() - started, 3),
            "directories_scanned": len(allocated_directories), "entries_examined": entries_seen,
            "excluded_entries": excluded, "unavailable_entries": errors,
            "truncated_scan": truncated, "scan_complete": not truncated,
            "sample_only": truncated or bool(excluded), "scope_filtered": True,
            "size_kind": "live_logical_file_bytes_and_allocated_blocks",
            "metadata_kind": "live_host_metadata_not_snapshot", "snapshot_only": False,
            "contents_read": False, "excludes": "protected paths, symlinks, hardlinks, special files and nested mounts"}


def summary(data: dict, path: str) -> str:
    coverage = "Incomplete scan: these are partial totals." if data["truncated_scan"] else "Scan completed within the permitted view."
    return (f"{path}: allocated {data['allocated_size_human']}; logical file size {data['logical_size_human']}. "
            f"{coverage} Excluded {data['excluded_entries']} protected/linked/special/mounted entries; "
            "this is not an unrestricted du total.")
