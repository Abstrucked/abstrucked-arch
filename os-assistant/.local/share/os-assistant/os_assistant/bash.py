"""Restricted command interface, never an unsandboxed model-supplied shell.

Read-only pipelines use audited argv in Bash, inside a read-only, filtered copy
of an approved folder. File mutations use fd-relative operations, not a host
shell: even a confirmation cannot authorize a script, symlink or protected path.
The denylist cannot recognize every sensitive filename; folder approval grants
content access to ordinary files within that folder.
"""

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import tempfile
import time
import unicodedata

from .contracts import PolicyError


FILE_BYTES = 1024 * 1024
SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_STAGES = 4
MAX_TOKENS = 64
METADATA_BYTES = 16 * 1024 ** 3
ASSISTANT_PACKAGE = Path(__file__).resolve().parents[4]
TRUSTED_HELPER_ROOTS = tuple(ASSISTANT_PACKAGE.parent / path for path in (
    "themes", "plugins", "scripts/.local/bin/display-detect", "scripts/config_syntax.py"))
READ_COMMANDS = frozenset({"pwd", "ls", "cat", "grep", "rg", "find", "head", "tail",
                           "wc", "sort", "uniq", "cut", "du", "df", "echo", "printf"})
WRITE_COMMANDS = frozenset({"mkdir", "touch", "cp", "mv", "rm"})
_FORMATS = {"%s": "", "%s\\n": "\n"}
_SHELL_OPERATORS = frozenset({";", "&", "&&", "||", "<", "<<", "<<<", "(", ")"})


@dataclass(frozen=True)
class CommandPlan:
    root: str
    cwd: str
    stages: tuple[tuple[str, ...], ...]
    operation: str = ""
    operands: tuple[str, ...] = ()
    text: str = ""
    selections: tuple[tuple[str, bool, bool], ...] = ()  # relative path, recurse, content needed

    @property
    def mutates(self) -> bool:
        return bool(self.operation)

    @property
    def live_usage(self) -> bool:
        return len(self.stages) == 1 and self.stages[0][0] == "/usr/bin/du"

    @property
    def argv(self) -> tuple[str, ...]:
        if self.mutates:
            if self.operation in ("write", "append"):
                return ("/usr/bin/printf", "%s", self.text,
                        ">>" if self.operation == "append" else ">", str(Path(self.root) / self.operands[0]))
            return ("/usr/bin/" + self.operation, "--", *(str(Path(self.root) / p) for p in self.operands))
        if self.live_usage:
            return self.stages[0]  # descriptive argv; guarded stat adapter, not native execution
        command = "set -o pipefail; " + " | ".join(shlex.join(stage) for stage in self.stages)
        return ("/usr/bin/bash", "--noprofile", "--norc", "-c", command)


def _protected(name: str) -> bool:
    from .policy import protected_name
    return protected_name(name) or name.lower() in {"auth.json", "tokens.json", ".curlrc", ".wgetrc"}


def _relative(root: str, cwd: str, value: str) -> str:
    if value == "~" or value.startswith("~/"):
        value = str(Path(value).expanduser())
    if (not value or len(value) > 512 or any(unicodedata.category(c).startswith("C") for c in value)
            or value.startswith(("~", "$"))):
        raise PolicyError("Bash paths must be literal, bounded paths inside the approved folder.")
    path = PurePosixPath(value)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            try:
                path = path.relative_to("/work")
            except ValueError:
                raise PolicyError("Bash cannot access paths outside its approved folder.") from None
    else:
        path = PurePosixPath(cwd) / path
    if (".." in path.parts or any(_protected(p) for p in path.parts)
            or any(c in str(path) for c in "*?[]")):
        raise PolicyError("Protected paths, parent traversal and pathname glob expansion are forbidden.")
    return str(path)


def _virtual(root: str, cwd: str, value: str) -> str:
    return str(PurePosixPath("/work") / _relative(root, cwd, value))


def _number(value: str, maximum: int = 1000) -> str:
    if not re.fullmatch(r"[0-9]{1,4}", value) or not 1 <= int(value) <= maximum:
        raise PolicyError("Bash count is outside the supported bounds.")
    return value


def _short_flags(value: str, letters: str) -> bool:
    return len(value) > 1 and value.startswith("-") and not value.startswith("--") and all(c in letters for c in value[1:])


def _read_stage(root: str, cwd: str, words: list[str], *, piped: bool = False,
                selections: list | None = None) -> tuple[str, ...]:
    name = words[0].removeprefix("/usr/bin/")
    if name not in READ_COMMANDS:
        raise PolicyError("Bash command is not in the audited command set; nothing executed.")
    values = words[1:]
    if name == "pwd":
        if any(v not in ("-L", "-P") for v in values):
            raise PolicyError("Unsupported pwd arguments.")
        return ("/usr/bin/pwd", *values)
    if name in ("echo", "printf"):
        if name == "echo":
            if values and values[0].startswith("-"):
                raise PolicyError("echo options are not supported.")
            return ("/usr/bin/printf", "%s\\n", " ".join(values))
        if len(values) != 2 or values[0] not in _FORMATS:
            raise PolicyError("printf supports only %s or %s\\n and one literal value.")
        return ("/usr/bin/printf", *values)
    if name == "find":
        position = 0
        target = "."
        if values and not values[0].startswith("-"):
            target, position = values[0], 1
        result = ["/usr/bin/find", _virtual(root, cwd, target)]
        if selections is not None:
            selections.append((_relative(root, cwd, target), True, False))
        while position < len(values):
            option = values[position]
            position += 1
            if option == "-print":
                result.append(option)
                continue
            if option not in {"-name", "-iname", "-type", "-maxdepth", "-mindepth"} or position >= len(values):
                raise PolicyError("find permits only name/type/depth filters and -print; no actions.")
            value = values[position]
            position += 1
            if ((option == "-type" and value not in {"f", "d"})
                    or (option in {"-maxdepth", "-mindepth"} and not re.fullmatch(r"[0-8]", value))
                    or (option in {"-name", "-iname"} and len(value) > 128)):
                raise PolicyError("Unsupported find filter.")
            result.extend((option, value))
        return tuple(result)

    short = {"ls": "aAlhndtSrR1F", "cat": "nbsETv", "grep": "EFnivwxcHhorRlsq",
             "rg": "nivwFcl", "head": "qv", "tail": "qv", "wc": "lwcmL",
             "sort": "nruVfh", "uniq": "cud", "cut": "s", "du": "shbk", "df": "hik"}
    options: list[str] = []
    paths: list[str] = []
    pattern: str | None = None
    explicit_pattern = False
    stopped = False
    index = 0
    while index < len(values):
        value = values[index]
        index += 1
        if not stopped and value == "--":
            stopped = True
            continue
        if not stopped and value.startswith("-") and value != "-":
            if _short_flags(value, short[name]):
                options.append(value)
                continue
            if name in ("grep", "rg") and value == "-e" and index < len(values):
                if pattern is not None:
                    raise PolicyError("Use either a positional search pattern or -e patterns, not both.")
                if len(values[index]) > 512:
                    raise PolicyError("Bash search pattern is too long.")
                options.extend((value, values[index]))
                index += 1
                explicit_pattern = True
                continue
            if name in ("head", "tail") and value in ("-n", "-c") and index < len(values):
                options.extend((value, _number(values[index], 8192 if value == "-c" else 1000)))
                index += 1
                continue
            if name in ("head", "tail") and re.fullmatch(r"-[nc][0-9]{1,4}", value):
                options.extend((value[:2], _number(value[2:], 8192 if value[1] == "c" else 1000)))
                continue
            if name == "cut" and value in ("-d", "-f", "-c", "-b") and index < len(values):
                parameter = values[index]
                index += 1
                if ((value == "-d" and len(parameter) != 1)
                        or (value != "-d" and not re.fullmatch(r"[0-9,-]{1,64}", parameter))):
                    raise PolicyError("Unsupported cut delimiter or field list.")
                options.extend((value, parameter))
                continue
            if name == "du" and value == "--apparent-size":
                options.append(value)
                continue
            raise PolicyError("Unsupported Bash option; dangerous and unknown options are never auto-approved.")
        if name in ("grep", "rg") and pattern is None and not explicit_pattern:
            if len(value) > 512:
                raise PolicyError("Bash search pattern is too long.")
            pattern = value
            continue
        if value == "-" and name in ("cat", "head", "tail", "wc", "sort", "uniq", "cut"):
            paths.append(value)
        else:
            paths.append(_virtual(root, cwd, value))
    if name in ("grep", "rg") and pattern is None and not explicit_pattern:
        raise PolicyError("grep/rg require a literal search pattern.")
    if name == "uniq" and len(paths) > 1:
        raise PolicyError("uniq output-file operands are forbidden.")
    if (name in ("ls", "du", "df") or (name == "rg" and not piped)) and not paths:
        paths = [_virtual(root, cwd, ".")]
    if name == "grep" and not paths and any(_short_flags(o, "EFnivwxcHhorRlsq") and ("r" in o or "R" in o) for o in options):
        paths = [_virtual(root, cwd, ".")]
    if name == "du":
        if len(paths) != 1:
            raise PolicyError("du supports one directory summary; use directory_usage for folder breakdowns.")
        if not any(option.startswith("-") and not option.startswith("--") and "s" in option for option in options):
            options.insert(0, "-s")
    if selections is not None and name != "df":
        for value in paths:
            if value == "-":
                continue
            relative = str(PurePosixPath(value).relative_to("/work"))
            recursive = name != "ls" or any("R" in o for o in options)
            selections.append((relative, recursive, name not in {"ls", "du"}))
    if name == "rg":
        options[:0] = ["--no-config", "--threads", "1", "--color", "never"]
    if name == "grep":
        options[:0] = ["--color=never"]
    if name == "sort":
        options[:0] = ["-S", "16M"]
    return ("/usr/bin/" + name, *options, "--", *((pattern,) if pattern is not None else ()), *paths)


def plan(config, arguments: dict) -> CommandPlan:
    root, command = arguments["root"], arguments["command"]
    if root not in config.bash_roots or not config.bash_enabled:
        raise PolicyError("Bash folder access is not explicitly enabled.")
    cwd = _relative(root, ".", arguments.get("cwd", "."))
    if "`" in command or "$(" in command or "${" in command:
        raise PolicyError("Shell substitution and variable expansion are forbidden.")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        words = list(lexer)
    except ValueError:
        raise PolicyError("Malformed Bash quoting; nothing executed.") from None
    if (not words or len(words) > MAX_TOKENS or any(word in _SHELL_OPERATORS for word in words)
            or any(re.fullmatch(r"[|;&<>()]+", word) and word not in {"|", ">", ">>"} for word in words)):
        raise PolicyError("Bash accepts bounded simple commands and read-only pipes, not command chains or scripts.")
    redirects = [i for i, word in enumerate(words) if word in {">", ">>"}]
    name = words[0].removeprefix("/usr/bin/")
    operation, operands, text = "", (), ""
    if redirects:
        position = redirects[0]
        if (len(redirects) != 1 or position != len(words) - 2 or "|" in words
                or name not in {"echo", "printf"}):
            raise PolicyError("Only literal echo/printf file writes support redirection, with confirmation.")
        _read_stage(root, cwd, words[:position])
        if name == "echo":
            text = " ".join(words[1:position]) + "\n"
        else:
            text = words[2] + _FORMATS[words[1]]
        operation = "append" if words[position] == ">>" else "write"
        operands = (_relative(root, cwd, words[-1]),)
    elif name in WRITE_COMMANDS:
        values = words[1:]
        if values and values[0] == "--":
            values = values[1:]
        if (len(values) != (2 if name in {"cp", "mv"} else 1)
                or any(v.startswith("-") or v in {"|", ">", ">>"} for v in values)):
            raise PolicyError("File commands support only literal operands, no recursive, force or other options.")
        operation = name
        operands = tuple(_relative(root, cwd, value) for value in values)
    if operation:
        if not config.bash_allow_writes or not config.actions_enabled:
            raise PolicyError("Bash writes require bash.allow_writes and actions.enabled, plus per-call approval.")
        if "." in operands or (len(operands) == 2 and operands[0] == operands[1]):
            raise PolicyError("Root mutation and identical source/destination paths are forbidden.")
        targets = operands[1:] if operation == "cp" else operands
        if any((Path(root) / target).is_relative_to(ASSISTANT_PACKAGE) for target in targets):
            raise PolicyError("Bash cannot modify the assistant's own package or permission code.")
        if any((Path(root) / target).is_relative_to(helper) for target in targets for helper in TRUSTED_HELPER_ROOTS):
            raise PolicyError("Bash cannot modify trusted theme/plugin/status helper code; use its dedicated tools.")
        return CommandPlan(root, cwd, (), operation, operands, text)
    stages: list[tuple[str, ...]] = []
    selections: list[tuple[str, bool, bool]] = []
    pending: list[str] = []
    for word in [*words, "|"]:
        if word == "|":
            if not pending:
                raise PolicyError("Empty Bash pipeline stage.")
            stages.append(_read_stage(root, cwd, pending, piped=bool(stages), selections=selections))
            pending = []
        elif any(c in word for c in "<>") and word in {">&", "&>", ">|"}:
            raise PolicyError("Unsupported Bash redirection.")
        else:
            pending.append(word)
    if len(stages) > MAX_STAGES:
        raise PolicyError("Bash pipeline exceeded its stage limit.")
    if len(stages) != 1 and any(stage[0] == "/usr/bin/du" for stage in stages):
        raise PolicyError("du summaries use guarded live metadata and cannot be piped; use directory_usage.")
    return CommandPlan(root, cwd, tuple(stages), selections=tuple(selections))


@contextmanager
def _root(path: str):
    from .policy import open_directory
    fd = open_directory(path)
    try:
        yield fd
    finally:
        os.close(fd)


def _mount_id(fd: int) -> str:
    """Detect same-device bind mounts too, using only fixed kernel fd metadata."""
    try:
        with open(f"/proc/self/fdinfo/{fd}", encoding="ascii") as stream:
            metadata = stream.read(4097)
        match = re.search(r"^mnt_id:\s+([0-9]+)$", metadata, re.MULTILINE)
        if len(metadata) > 4096 or match is None:
            raise OSError
        return match[1]
    except (OSError, UnicodeError):
        raise PolicyError("Bash requires Linux mount identity checks; no unsafe fallback.") from None


@contextmanager
def _directory(root_fd: int, relative: str):
    fd = os.dup(root_fd)
    try:
        device, mount = os.fstat(root_fd).st_dev, _mount_id(root_fd)
        for part in PurePosixPath(relative).parts:
            if part == ".":
                continue
            new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            try:
                if os.fstat(new_fd).st_dev != device or _mount_id(new_fd) != mount:
                    raise PolicyError("Bash refuses nested filesystem mounts.")
            except BaseException:
                os.close(new_fd)
                raise
            os.close(fd)
            fd = new_fd
        yield fd
    finally:
        os.close(fd)


def _identity(info, *, content: bool = False) -> tuple:
    fields = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink)
    return (*fields, info.st_size, info.st_mtime_ns, info.st_ctime_ns) if content else fields


def _regular(info) -> None:
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or info.st_size > FILE_BYTES):
        raise PolicyError("File operation requires an owned regular file, no links, at most 1 MiB.")


def _trusted_executable(value: str) -> tuple:
    try:
        path = Path(value).resolve(strict=True)
        if not path.is_relative_to("/usr") or path.is_relative_to("/usr/local"):
            raise OSError
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
            raise OSError
        for candidate in (path, *path.parents):
            metadata = candidate.stat()
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                raise OSError
        return (value, str(path), *_identity(info, content=True))
    except (OSError, ValueError, RuntimeError):
        raise PolicyError("Bash requires trusted, root-owned executables and bubblewrap; no unsafe fallback.") from None


def verification(command: CommandPlan, root_fd: int | None = None) -> str:
    executables = set() if command.live_usage else {"/usr/bin/bash", "/usr/bin/bwrap", "/usr/bin/prlimit"}
    if not command.mutates and not command.live_usage:
        executables.update(stage[0] for stage in command.stages)
    fields = [_trusted_executable(value) for value in sorted(executables)]
    try:
        context = _root(command.root) if root_fd is None else nullcontext(root_fd)
        with context as root_fd, _directory(root_fd, command.cwd) as cwd_fd:
            fields.append(("root", _identity(os.fstat(root_fd))))
            fields.append(("cwd", _identity(os.fstat(cwd_fd))))
            if command.live_usage:
                target = str(PurePosixPath(command.stages[0][-1]).relative_to("/work"))
                with _directory(root_fd, target) as target_fd:
                    fields.append(("usage_target", _identity(os.fstat(target_fd))))
            for value in command.operands:
                path = PurePosixPath(value)
                with _directory(root_fd, str(path.parent)) as parent_fd:
                    fields.append((str(path.parent), _identity(os.fstat(parent_fd))))
                    try:
                        info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        if value == command.operands[0] and command.operation in {"cp", "mv", "rm"}:
                            raise PolicyError("File command source does not exist.") from None
                        fields.append((value, "missing"))
                    else:
                        if command.operation == "mkdir":
                            raise PolicyError("mkdir supports creating a new directory only.")
                        _regular(info)
                        operand_fd = os.open(path.name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                        try:
                            if (_mount_id(operand_fd) != _mount_id(parent_fd)
                                    or _identity(os.fstat(operand_fd), content=True) != _identity(info, content=True)):
                                raise PolicyError("Bash operand is mounted or changed; nothing executed.")
                        finally:
                            os.close(operand_fd)
                        fields.append((value, _identity(info, content=True)))
        return hashlib.sha256(repr(fields).encode()).hexdigest()
    except OSError:
        raise PolicyError("Bash working folder or operand is unavailable, linked or unsafe.") from None


def prepare(config, arguments: dict) -> tuple[dict, bool, tuple[str, ...], str]:
    command = plan(config, arguments)
    normalized = {**arguments, "cwd": command.cwd}
    # The terminal preview has an 8 KiB character cap. Never let escaped Unicode
    # hide a mutation's destination/argv behind truncation before human approval.
    if command.mutates and len(json.dumps({"arguments": normalized, "argv": command.argv}, ensure_ascii=True)) > 6000:
        raise PolicyError("Bash mutation is too large for an exact terminal preview; use a shorter command.")
    return normalized, command.mutates, command.argv, verification(command)


def sandbox_argv(snapshot: str, command: CommandPlan, timeout: int = 5) -> tuple[str, ...]:
    # Debian/Ubuntu keep the ELF loader in /usr/lib64 (Arch: usr/lib64 -> lib); fall back to usr/lib without it.
    lib64 = "usr/lib64" if os.path.exists("/usr/lib64") else "usr/lib"
    return ("/usr/bin/prlimit", "--as=134217728", "--nofile=64", "--core=0",
            "--fsize=" + str(SNAPSHOT_BYTES), "--cpu=" + str(timeout), "--",
            "/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--assert-userns-disabled",
            "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
            "--setenv", "PATH", "/usr/bin", "--setenv", "LC_ALL", "C", "--setenv", "HOME", "/nonexistent",
            "--ro-bind", "/usr", "/usr", "--tmpfs", "/usr/local", "--remount-ro", "/usr/local",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib", "--symlink", lib64, "/lib64",
            "--proc", "/proc", "--dev", "/dev", "--size", str(SNAPSHOT_BYTES), "--tmpfs", "/tmp",
            "--ro-bind", snapshot, "/work", "--remount-ro", "/", "--chdir", str(PurePosixPath("/work") / command.cwd),
            *command.argv)


def snapshot(root: str, destination: Path, config, command: CommandPlan | None = None,
             expected_verification: str = "") -> dict:
    entries_seen = files = bytes_copied = excluded = placeholders = 0
    truncated = False
    deadline = time.monotonic() + config.scan_seconds
    with _root(root) as root_fd, _root(str(destination)) as destination_fd:
        if expected_verification and (command is None or verification(command, root_fd) != expected_verification):
            raise PolicyError("Bash source folder changed; no content copied.")
        device, mount = os.fstat(root_fd).st_dev, _mount_id(root_fd)
        selections = command.selections if command is not None else ((".", True, True),)

        def contains(parent: str, child: str) -> bool:
            return PurePosixPath(child).is_relative_to(PurePosixPath(parent))

        def relevant(path: str) -> bool:
            return any(path == target or contains(path, target) or (recurse and contains(target, path))
                       or (not recurse and str(PurePosixPath(path).parent) == target)
                       for target, recurse, _ in selections)

        def descend(path: str) -> bool:
            return any(path == target or contains(path, target) or (recurse and contains(target, path))
                       for target, recurse, _ in selections)

        def content_needed(path: str) -> bool:
            return any(content and (path == target or (recurse and contains(target, path)))
                       for target, recurse, content in selections)

        # Even commands without file operands need their validated cwd present.
        if command is not None:
            current_fd = os.dup(destination_fd)
            try:
                for component in PurePosixPath(command.cwd).parts:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                       dir_fd=current_fd)
                    os.close(current_fd)
                    current_fd = child_fd
            finally:
                os.close(current_fd)

        def walk(parent_fd: int, output_fd: int, relative: str, depth: int) -> None:
            nonlocal entries_seen, files, bytes_copied, excluded, placeholders, truncated
            with os.scandir(parent_fd) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > config.scan_entries or time.monotonic() >= deadline:
                        truncated = True
                        return
                    if _protected(entry.name):
                        excluded += 1
                        continue
                    path = str(PurePosixPath(relative) / entry.name)
                    if not relevant(path):
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if info.st_dev != device:
                            excluded += 1
                        elif stat.S_ISDIR(info.st_mode):
                            if descend(path) and depth >= config.scan_depth:
                                truncated = True
                                excluded += 1
                                continue
                            child_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                               dir_fd=parent_fd)
                            try:
                                if _mount_id(child_fd) != mount:
                                    excluded += 1
                                    continue
                                if _identity(os.fstat(child_fd)) != _identity(info):
                                    truncated = True
                                    continue
                                try:
                                    os.mkdir(entry.name, mode=0o700, dir_fd=output_fd)
                                except FileExistsError:
                                    pass  # cwd ancestors may already have been created
                                child_output_fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                                          dir_fd=output_fd)
                                try:
                                    if descend(path):
                                        walk(child_fd, child_output_fd, path, depth + 1)
                                finally:
                                    os.close(child_output_fd)
                            finally:
                                os.close(child_fd)
                        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not content_needed(path):
                            if info.st_size > METADATA_BYTES:
                                truncated = True
                                excluded += 1
                                continue
                            # Sparse metadata proxy, never consumed by a content-reading
                            # stage: preserves logical size without reading source bytes.
                            source_fd = os.open(entry.name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                            try:
                                if (_mount_id(source_fd) != mount
                                        or _identity(os.fstat(source_fd), content=True) != _identity(info, content=True)):
                                    excluded += 1
                                    continue
                                fd = os.open(entry.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                             0o600, dir_fd=output_fd)
                                try:
                                    os.ftruncate(fd, info.st_size)
                                    placeholders += 1
                                finally:
                                    os.close(fd)
                            finally:
                                os.close(source_fd)
                        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= FILE_BYTES:
                            if bytes_copied + info.st_size > SNAPSHOT_BYTES:
                                truncated = True
                                excluded += 1
                                continue
                            fd = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
                            try:
                                before = os.fstat(fd)
                                if _mount_id(fd) != mount:
                                    excluded += 1
                                    continue
                                if not stat.S_ISREG(before.st_mode) or _identity(before, content=True) != _identity(info, content=True):
                                    truncated = True
                                    continue
                                with os.fdopen(fd, "rb", closefd=False) as stream:
                                    content = stream.read(min(FILE_BYTES, SNAPSHOT_BYTES - bytes_copied) + 1)
                                if (len(content) > FILE_BYTES or bytes_copied + len(content) > SNAPSHOT_BYTES
                                        or _identity(os.fstat(fd), content=True) != _identity(before, content=True)):
                                    truncated = True
                                    excluded += 1
                                    continue
                                target_fd = os.open(entry.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                                    0o600, dir_fd=output_fd)
                                with os.fdopen(target_fd, "wb") as target:
                                    target.write(content)
                                files += 1
                                bytes_copied += len(content)
                            finally:
                                os.close(fd)
                        else:
                            excluded += 1
                    except OSError:
                        truncated = True
                        excluded += 1
                    if truncated and (entries_seen > config.scan_entries or time.monotonic() >= deadline):
                        return
        if selections:
            walk(root_fd, destination_fd, ".", 0)
    return {"snapshot_only": True, "sample_only": True, "files_copied": files,
            "bytes_copied": bytes_copied, "metadata_placeholders": placeholders,
            "excluded_entries": excluded, "truncated_snapshot": truncated,
            "excludes": "protected names, symlinks, hardlinks, special files, nested mounts; content over 1 MiB or metadata over 16 GiB",
            "metadata_kind": "filtered_copy_not_live_host_metadata"}


def run_readonly(call, config, capture) -> dict:
    command = plan(config, call.argument_dict())
    if command.mutates:
        raise PolicyError("A mutating command cannot use automatic Bash execution.")
    if command.live_usage:
        from . import filesystem
        target = str(PurePosixPath(command.stages[0][-1]).relative_to("/work"))
        with _root(command.root) as root_fd:
            if verification(command, root_fd) != call.verification:
                raise PolicyError("Size target changed; nothing scanned.")
            data = filesystem.usage(root_fd, target, config)
        apparent = False
        unit = "k"
        for option in command.stages[0][1:command.stages[0].index("--")]:
            if option == "--apparent-size":
                apparent = True
            else:
                for flag in option[1:]:
                    if flag == "b":
                        apparent = True
                    if flag in "hbk":
                        unit = flag
        size = data["total_size_bytes"] if apparent else data["allocated_size_bytes"]
        shown = filesystem.human_bytes(size) if unit == "h" else str(size if unit == "b" else (size + 1023) // 1024)
        path = str(Path(command.root) / target)
        return {**data, "root": command.root, "cwd": command.cwd, "path": target, "exit_code": 0,
                "stdout": f"{shown}\t{path}\n", "stderr": "", "persistent_host_writes": False,
                 "temporary_snapshot_created": False, "network_enabled": False,
                 "reported_size_bytes": size, "reported_size_kind": "logical" if apparent else "allocated",
                 "reported_unit": unit,
                 "executor": "guarded_live_size_metadata", "summary": filesystem.summary(data, path)}
    with tempfile.TemporaryDirectory(prefix="os-assistant-bash-", dir="/tmp") as temporary:
        metadata = snapshot(command.root, Path(temporary), config, command, call.verification)
        if verification(command) != call.verification:
            raise PolicyError("Bash source/working folder changed; no command executed.")
        code, stdout, stderr = capture(sandbox_argv(temporary, command, config.tool_timeout), config.tool_timeout,
                                       environment={"PATH": "/usr/bin", "LC_ALL": "C"})
    return {**metadata, "root": command.root, "cwd": command.cwd, "exit_code": code,
            "stdout": stdout, "stderr": stderr, "persistent_host_writes": False,
            "temporary_snapshot_created": True, "network_enabled": False,
            "executor": "read_only_bubblewrap_snapshot"}


def _read_operand(root_fd: int, path: PurePosixPath) -> bytes:
    with _directory(root_fd, str(path.parent)) as parent_fd:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            _regular(info)
            if _mount_id(fd) != _mount_id(parent_fd):
                raise PolicyError("Bash refuses nested filesystem mounts.")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                content = stream.read(FILE_BYTES + 1)
            if len(content) > FILE_BYTES or _identity(os.fstat(fd), content=True) != _identity(info, content=True):
                raise PolicyError("File changed or exceeded its limit; no output file published.")
            return content
        finally:
            os.close(fd)


def _publish(root_fd: int, path: PurePosixPath, content: bytes) -> None:
    if len(content) > FILE_BYTES:
        raise PolicyError("File output exceeds the 1 MiB limit.")
    with _directory(root_fd, str(path.parent)) as parent_fd:
        # An fd-relative private temporary file is atomically replaced into the
        # approved destination; never truncate a potentially raced hardlink.
        temporary = ".os-assistant-" + os.urandom(16).hex()
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(content)
                stream.flush()
            os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        finally:
            os.close(fd)
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def run_mutation(call, config) -> dict:
    command = plan(config, call.argument_dict())
    if not command.mutates:
        raise PolicyError("Bash file operation changed; nothing executed.")
    paths = tuple(PurePosixPath(p) for p in command.operands)
    with _root(command.root) as root_fd:
        if verification(command, root_fd) != call.verification:
            raise PolicyError("Bash file operation changed; nothing executed.")
        if command.operation in {"write", "append", "cp"}:
            if command.operation == "cp":
                content, destination = _read_operand(root_fd, paths[0]), paths[1]
            else:
                content, destination = command.text.encode("utf-8"), paths[0]
                if command.operation == "append":
                    try:
                        content = _read_operand(root_fd, destination) + content
                    except FileNotFoundError:
                        pass
            _publish(root_fd, destination, content)
        elif command.operation == "mv":
            with _directory(root_fd, str(paths[0].parent)) as source_fd, _directory(root_fd, str(paths[1].parent)) as target_fd:
                os.replace(paths[0].name, paths[1].name, src_dir_fd=source_fd, dst_dir_fd=target_fd)
        else:
            with _directory(root_fd, str(paths[0].parent)) as parent_fd:
                if command.operation == "mkdir":
                    os.mkdir(paths[0].name, mode=0o700, dir_fd=parent_fd)
                elif command.operation == "rm":
                    os.unlink(paths[0].name, dir_fd=parent_fd)
                elif command.operation == "touch":
                    fd = os.open(paths[0].name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 0o600, dir_fd=parent_fd)
                    try:
                        _regular(os.fstat(fd))
                        if _mount_id(fd) != _mount_id(parent_fd):
                            raise PolicyError("Bash refuses nested filesystem mounts.")
                        os.utime(fd, None)
                    finally:
                        os.close(fd)
    return {"exit_code": 0, "stdout": "", "stderr": "", "root": command.root, "cwd": command.cwd,
            "changed_paths": list(command.operands), "executor": "guarded_fd_file_operation",
            "message": "Approved file operation completed; no host shell or script executed."}
