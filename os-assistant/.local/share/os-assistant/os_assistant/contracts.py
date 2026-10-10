"""Shared immutable contracts. Model output never grants execution authority."""

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


class AssistantError(Exception):
    """An error with a deliberately safe, user-facing message."""

    exit_code = 4


class ConfigurationError(AssistantError):
    exit_code = 2


class PolicyError(AssistantError):
    exit_code = 3


class ToolSchemaError(PolicyError):
    """A known tool's missing/unknown fields, with no I/O or execution."""


class ModelError(AssistantError):
    exit_code = 5


class FileRecord(TypedDict):
    relative_path: str
    name: str
    size_bytes: int
    allocated_size_bytes: NotRequired[int]


@dataclass(frozen=True)
class PreparedCall:
    name: str
    arguments: tuple[tuple[str, Any], ...]
    mutates: bool = False
    argv: tuple[str, ...] = ()
    verification: str = ""

    def argument_dict(self) -> dict[str, Any]:
        return dict(self.arguments)


@dataclass(frozen=True)
class ToolResult:
    name: str
    status: str
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"tool": self.name, "status": self.status, "data": self.data}
