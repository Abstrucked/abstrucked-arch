#!/usr/bin/env python3
"""Read-only syntax validation for JSON, JSONC, TOML, and YAML data files."""
import argparse
import json
from pathlib import Path
import re
import sys


class ConfigSyntaxError(ValueError):
    """A safe-to-display syntax error that never includes document contents."""


def _position(text, offset):
    line = text.count("\n", 0, offset) + 1
    previous = text.rfind("\n", 0, offset)
    return line, offset - previous


def _jsonc_text(text):
    """Remove JSONC comments and trailing commas without changing locations."""
    chars = list(text)
    i = 0
    in_string = False
    escaped = False
    while i < len(chars):
        char = chars[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            i += 1
            continue
        if char == "/" and i + 1 < len(chars) and chars[i + 1] in ("/", "*"):
            start = i
            block = chars[i + 1] == "*"
            i += 2
            if block:
                end = text.find("*/", i)
                if end < 0:
                    line, col = _position(text, start)
                    raise ConfigSyntaxError(f"unterminated comment at line {line}, column {col}")
                end += 2
            else:
                end = i
                while end < len(chars) and chars[end] not in "\r\n":
                    end += 1
            for j in range(start, end):
                if chars[j] not in "\r\n":
                    chars[j] = " "
            i = end
            continue
        i += 1

    # A second string-aware pass removes commas followed by a closing delimiter.
    result = list(chars)
    i = 0
    in_string = escaped = False
    while i < len(result):
        char = result[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == ",":
            preceding = i - 1
            while preceding >= 0 and result[preceding].isspace():
                preceding -= 1
            following = i + 1
            while following < len(result) and result[following].isspace():
                following += 1
            can_end_value = (preceding >= 0 and
                             result[preceding] in '" ]}0123456789el')
            if (can_end_value and following < len(result) and
                    result[following] in "]}"):
                result[i] = " "
        i += 1
    return "".join(result)


def _reject_constant(_value):
    raise ValueError("non-standard numeric constant")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _parse_json(text, *, jsonc, fragment, require_object):
    source = "{" + text + "\n}" if fragment else text
    if jsonc:
        source = _jsonc_text(source)
    try:
        data = json.loads(source, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        line, col = _position(source, error.pos)
        if fragment:
            # The leading wrapper occupies the first column of the first line.
            col = max(1, col - 1) if line == 1 else col
        raise ConfigSyntaxError(f"invalid JSON syntax at line {line}, column {col}") from None
    except ValueError as error:
        # Never surface parser values/keys; they may contain private data.
        match = re.search(r"line (\d+) column (\d+)", str(error))
        location = f" at line {match.group(1)}, column {match.group(2)}" if match else ""
        raise ConfigSyntaxError(f"invalid JSON data{location}") from None
    if (require_object or fragment) and not isinstance(data, dict):
        raise ConfigSyntaxError("top-level value must be an object")


def _location_from_error(error, text):
    line = getattr(error, "lineno", None) or getattr(error, "line", None)
    col = getattr(error, "colno", None) or getattr(error, "column", None)
    mark = getattr(error, "problem_mark", None)
    if mark is not None:
        line = mark.line + 1
        col = mark.column + 1
    if line is None:
        match = re.search(r"line (\d+)(?:, column (\d+))?", str(error), re.IGNORECASE)
        if match:
            line = int(match.group(1))
            col = int(match.group(2) or 1)
    return f" at line {line}, column {col or 1}" if line else ""


def validate_file(path, *, format=None, fragment=False, require_object=False):
    """Validate one data file; raises ConfigSyntaxError with safe diagnostics."""
    path = Path(path)
    kind = (format or path.suffix.lstrip(".")).lower()
    if kind == "yml":
        kind = "yaml"
    if kind not in ("json", "jsonc", "toml", "yaml"):
        raise ConfigSyntaxError(f"{path}: unsupported data format: {kind or '(none)'}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ConfigSyntaxError(f"{path}: unable to read UTF-8 data file") from None
    try:
        if kind in ("json", "jsonc"):
            _parse_json(text, jsonc=(kind == "jsonc"), fragment=fragment,
                        require_object=require_object)
        elif kind == "toml":
            import tomllib
            tomllib.loads(text)
        else:
            try:
                import yaml
            except ImportError:
                raise ConfigSyntaxError(
                    "YAML validation requires PyYAML (python3-yaml)"
                ) from None
            yaml.safe_load(text)
    except ConfigSyntaxError as error:
        raise ConfigSyntaxError(f"{path}: {error}") from None
    except Exception as error:
        location = _location_from_error(error, text)
        raise ConfigSyntaxError(f"{path}: invalid {kind.upper()} syntax{location}") from None
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonc", action="store_true", help="parse input as JSONC")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--object", action="store_true", help="require a top-level object")
    group.add_argument("--fragment", action="store_true", help="parse object-member fragment")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_file(args.path, format="jsonc" if args.jsonc else None,
                      fragment=args.fragment, require_object=args.object)
    except ConfigSyntaxError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
