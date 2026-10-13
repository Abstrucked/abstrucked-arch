"""Conservative literal-command comparisons; never an execution authority."""

import re
import shlex

from . import bash


_PREFIX = re.compile(
    r"^(?:please\s+)?(?:use\s+(?:bash|the terminal)\s+to\s+(?:run|execute)|run|execute)\s+",
    re.IGNORECASE,
)
_FOLDER = re.compile(
    r"\s+in\s+(?:(?:my|the)\s+approved\s+(?:dotfiles\s+)?(?:folder|directory)|"
    r"this\s+(?:folder|directory))\.?\s*$", re.IGNORECASE,
)
_PROSE = re.compile(
    r"\b(?:in|using|with|to|and|then|instead|after|before|if|unless|because|"
    r"not|never|avoid|without|explain|describe|example)\b", re.IGNORECASE,
)
_OUTPUT = re.compile(
    r"\s+(?:and\s+(?:show|print|report|explain|describe)|"
    r"to\s+(?:display|find|locate|list|count|print|report|show))\b", re.IGNORECASE,
)
_AMBIGUOUS = re.compile(
    r"\b(?:if|unless|instead|not|never|avoid|without|rather|then|run|execute|use)\b",
    re.IGNORECASE,
)


def _unquoted(text: str) -> str:
    """Mask quoted/escaped data without changing indices of an outside suffix."""
    quote = ""
    escaped = False
    result = []
    for char in text:
        if escaped:
            result.append("\0")
            escaped = False
        elif char == "\\" and quote != "'":
            result.append("\0")
            escaped = True
        elif quote:
            result.append("\0")
            if char == quote:
                quote = ""
        elif char in "'\"":
            result.append("\0")
            quote = char
        else:
            result.append(char)
    return "".join(result)


def literal_command(prompt: str) -> str | None:
    """Extract only a single leading literal directive, never general prose.

    Backticks delimit the user's command, not a shell substitution. For unquoted
    commands only a fixed approved-folder suffix is removed, outside quotes;
    filenames' punctuation is never trimmed. Ambiguous prose stays with the
    model/name-only guard. Auditing and permissions still belong to Bash/Policy.
    """
    prompt = prompt.strip()
    prefix = _PREFIX.match(prompt)
    if prefix is None:
        return None
    payload = prompt[prefix.end():].strip()
    if payload.startswith("`"):
        end = payload.find("`", 1)
        if end < 0 or payload.count("`") != 2:
            return None
        suffix = payload[end + 1:]
        output = _OUTPUT.match(suffix) is not None and _AMBIGUOUS.search(_unquoted(suffix)) is None
        if suffix.strip() not in ("", ".") and _FOLDER.fullmatch(suffix) is None and not output:
            return None
        candidate = payload[1:end].strip()
    else:
        outside = _unquoted(payload)
        folder = _FOLDER.search(outside)
        candidate = payload[:folder.start()].rstrip() if folder else payload
        if _PROSE.search(_unquoted(candidate)):
            return None
    try:
        lexer = shlex.shlex(candidate, posix=True, punctuation_chars="|;&<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        name = next(lexer).removeprefix("/usr/bin/")
    except (StopIteration, ValueError):
        return None
    return candidate if name in bash.READ_COMMANDS | bash.WRITE_COMMANDS else None


def command_key(command: bash.CommandPlan) -> tuple:
    """Compare audited effects, preserving ordered options, stages and targets.

    Only simple ls a/l/h switches commute here. Do not sort arbitrary flags:
    output-format/sort modes, numeric options and pipeline order can conflict.
    Whitespace, quoting and in-root absolute/relative aliases are already
    normalized by the audited planner. No file or executable probing occurs.
    """
    stages = []
    for stage in command.stages:
        if stage[0] == "/usr/bin/ls":
            index = stage.index("--")
            options = stage[1:index]
            if all(bash._short_flags(option, "alh") for option in options):
                flags = "".join(sorted(set("".join(option[1:] for option in options))))
                stage = (stage[0], flags, *stage[index:])
        stages.append(stage)
    return (command.root, command.cwd, tuple(stages), command.operation,
            command.operands, command.text)
