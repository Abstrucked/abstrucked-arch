"""Small, explicit read-only chat grammar. It selects tools, never permissions."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import shlex

from . import bash
from .config import normalized_root
from .contracts import ConfigurationError, PolicyError
from .intent import _unquoted


@dataclass(frozen=True)
class SizeRequest:
    target: str | None = None
    metric: str = "size"


@dataclass(frozen=True)
class OutputRequest:
    question: str
    json_output: bool = False
    details: bool = False


def output_request(prompt: str) -> OutputRequest:
    """Output modifiers outside quotes, not command operands or permissions."""
    question = prompt.strip()
    outside = _unquoted(question)
    # Unquoted literal shell text must not be rewritten: 'echo as JSON' means
    # exactly that text. Backtick-delimited commands have an explicit boundary.
    directive = re.match(r"^(?:please\s+)?(?:run|execute|use)\s+", question, re.I)
    if directive and not re.match(
        r"^(?:please\s+)?(?:run|execute|use\s+(?:bash|the\s+terminal)\s+to\s+(?:run|execute))\s+`[^`]+`", question, re.I,
    ):
        return OutputRequest(question)
    match = re.search(r"\s+(?:as\s+(?:raw\s+)?json|in\s+json(?:\s+format)?|(?:with|in)\s+detail(?:s)?|in\s+plain\s+english)\.?\??$", outside, re.I)
    if match is None:
        return OutputRequest(question)
    suffix = outside[match.start():].lower()
    return OutputRequest(question[:match.start()].rstrip(), "json" in suffix, "detail" in suffix)


_POLITE = re.compile(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?", re.IGNORECASE)
_ACTION = re.compile(
    r"^(?:use\s+bash\s+and\s+)?(?:(?:show|tell|give)\s+me\s+|"
    r"(?:check|measure|calculate|report|get|find)(?:\s+(?:me|out))?\s+)?", re.IGNORECASE,
)
_SIZE_PATTERNS = tuple(re.compile(pattern + r"\??", re.IGNORECASE) for pattern in (
    r"(?:what(?:\s+is|'s)\s+)?(?:the\s+)?(?:(?:recursive|total|folder|directory)\s+)*size(?:\s+(?:of|for)\s+(?P<target>.+?))?",
    r"(?:what(?:\s+is|'s)\s+)?(?P<target>this\s+(?:folder|directory)|the\s+current\s+(?:folder|directory))'s\s+(?:recursive\s+)?size",
    r"how\s+big\s+is\s+(?P<target>.+?)",
    r"how\s+much\s+(?:disk\s+)?space\s+does\s+(?P<target>.+?)\s+(?:use|take|occupy)",
    r"(?:recursive\s+)?(?:allocated\s+)?disk\s+usage(?:\s+and\s+logical\s+file\s+bytes)?\s+(?:of|for)\s+(?P<target>.+?)",
    r"(?:what(?:\s+is|'s)\s+)?(?:the\s+)?(?:(?:recursive|total|logical|allocated)\s+)*size\s+(?:of|for)\s+(?P<target>.+?)",
    r"(?:what(?:\s+is|'s)\s+)?(?:the\s+)?(?:allocated\s+and\s+logical|logical\s+and\s+allocated)\s+size\s+(?:of|for)\s+(?P<target>.+?)",
))
_COUNT_PATTERNS = tuple(re.compile(pattern + r"\??", re.IGNORECASE) for pattern in (
    r"(?:what(?:\s+is|'s)\s+)?(?:the\s+)?(?:total\s+|recursive\s+)?(?:number|count)\s+of\s+files(?:\s+(?:in|inside|under|of|for)\s+(?P<target>.+?))?",
    r"(?:recursive\s+)?file\s+count(?:\s+(?:in|of|for)\s+(?P<target>.+?))?",
    r"how\s+many\s+files\s+(?:are\s+)?(?:there\s+)?(?:in|inside|under)\s+(?P<target>.+?)",
    r"how\s+many\s+files\s+does\s+(?P<target>.+?)\s+(?:have|contain)",
    r"count\s+(?:the\s+)?files(?:\s+(?:in|inside|under)\s+(?P<target>.+?))?",
))
_DEFAULT_REFERENCES = {
    ".", "folder", "directory", "the folder", "the directory", "this folder", "this directory", "current folder", "current directory",
    "the current folder", "the current directory", "my approved folder",
    "the approved folder", "my approved dotfiles folder", "the approved dotfiles folder",
}
_LABEL = re.compile(r"\s+(?:folder|directory)\.?$", re.IGNORECASE)
_WHICH_FOLDER = re.compile(
    r"(?:which\s+(?:folder|directory)\s+(?:was\s+that|did\s+you\s+(?:check|measure))|"
    r"what\s+(?:folder|directory)\s+did\s+you\s+(?:check|measure))\??", re.IGNORECASE,
)


def _target(text: str) -> str | None:
    text = text.strip()
    if (text.casefold() in _DEFAULT_REFERENCES
            or (text.endswith(".") and text[:-1].casefold() in _DEFAULT_REFERENCES - {"."})):
        return "."
    text = re.sub(r"^the\s+", "", text, count=1, flags=re.IGNORECASE)
    suffix = _LABEL.search(_unquoted(text))
    if suffix:
        text = text[:suffix.start()].rstrip()
    # Only one literal location, not mixed prose/actions. Quotes allow spaces;
    # their contents remain path data and are never sent to a host shell.
    try:
        words = shlex.split(text)
    except ValueError:
        return None
    if len(words) != 1 or not words[0] or len(words[0]) > 512:
        return None
    if any(char in words[0] for char in "`;|&<>\n\r"):
        return None
    return words[0]


def size_request(prompt: str) -> SizeRequest | None:
    text = _POLITE.sub("", prompt.strip(), count=1)
    text = _ACTION.sub("", text, count=1)
    patterns = [(pattern, "files") for pattern in _COUNT_PATTERNS]
    patterns.extend((pattern, "size") for pattern in _SIZE_PATTERNS)
    # 'Count files' uses count as a verb; other requests allow 'check/show me'.
    if prompt.strip().lower().startswith("count "):
        text = prompt.strip()
    for pattern, selected in patterns:
        match = pattern.fullmatch(text)
        if match:
            target = match.groupdict().get("target")
            if selected != "files":
                # A folder named 'logical' or 'allocated' is only path data.
                qualifiers = text[:match.start("target")] if target is not None else text
                if re.search(r"\blogical\b", qualifiers, re.I):
                    selected = "both" if re.search(r"\b(?:allocated|disk\s+usage)\b", qualifiers, re.I) else "logical"
            if target is None:
                return SizeRequest(metric=selected)
            location = _target(target)
            return SizeRequest(location, selected) if location is not None else None
    return None


def folder_answer(prompt: str, *, roots: tuple[str, ...] = (), allow_bare_name: bool = False) -> SizeRequest | None:
    location = _target(prompt)
    named = allow_bare_name and any(location in {Path(root).name, Path(root).name.lstrip(".")} for root in roots)
    if (location is None
            or location.casefold() in {"yes", "no", "ok", "okay", "thanks", "continue", "help", "quit", "reset", "hi", "hello"}
            or location in bash.READ_COMMANDS | bash.WRITE_COMMANDS
            or (not named and not location.startswith(("/", "~", ".")))):
        return None
    return SizeRequest(location)


def asks_which_folder(prompt: str) -> bool:
    return _WHICH_FOLDER.fullmatch(prompt.strip()) is not None


def resolve_size(request: SizeRequest, roots: tuple[str, ...], default: str | None) -> dict | None:
    """Pure lexical resolution inside configured roots; no probing or grants."""
    target = request.target
    if target is None or target == ".":
        return {"root": default, "path": "."} if default is not None else None
    if target.startswith(("/", "~")):
        try:
            absolute = normalized_root(target)
        except ConfigurationError:
            raise PolicyError("Folder paths must be literal approved paths without parent traversal; nothing scanned.") from None
        candidates = [root for root in roots if PurePosixPath(absolute).is_relative_to(root)]
        if not candidates:
            raise PolicyError("That folder is outside the approved roots; nothing scanned.")
        root = max(candidates, key=lambda value: len(PurePosixPath(value).parts))
        return {"root": root, "path": bash._relative(root, ".", absolute)}
    named = [root for root in roots if target in {Path(root).name, Path(root).name.lstrip(".")}]
    if len(named) == 1:
        return {"root": named[0], "path": "."}
    if named or default is None:
        return None
    return {"root": default, "path": bash._relative(default, ".", target)}
