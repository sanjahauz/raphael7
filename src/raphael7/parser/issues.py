"""Problems found while parsing, and how strict mode reacts to them.

Every problem gets a stable ``code`` (e.g. ``"bad-escape"``) so that `scan`
can count and group them across a whole feed.
"""

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    # The structure is broken (no MSH, invalid delimiters, bad segment ID).
    # Strict mode raises on these.
    ERROR = "error"
    # Off-spec but still parsed without ambiguity (\n line endings, unknown
    # escape sequences). Recorded in both modes, never raised.
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ParseIssue:
    code: str
    message: str
    severity: Severity = Severity.WARNING
    line: int | None = None  # 1-based line in the input
    location: str | None = None  # e.g. "PID-5"

    def __str__(self) -> str:
        text = f"{self.severity}: {self.code}: {self.message}"
        where = []
        if self.line:
            where.append(f"line {self.line}")
        if self.location:
            where.append(self.location)
        if where:
            text += f" ({' '.join(where)})"
        return text


class ParseError(ValueError):
    """Raised in strict mode on the first error-level issue."""

    def __init__(self, issue: ParseIssue):
        super().__init__(str(issue))
        self.issue = issue


class IssueLog:
    """Collects issues; in strict mode an error-level issue raises at once."""

    def __init__(self, strict: bool):
        self.strict = strict
        self.issues: list[ParseIssue] = []

    def add(self, issue: ParseIssue) -> None:
        if self.strict and issue.severity is Severity.ERROR:
            raise ParseError(issue)
        self.issues.append(issue)

    def error(self, code: str, message: str, *, line=None, location=None) -> None:
        self.add(ParseIssue(code, message, Severity.ERROR, line, location))

    def warning(self, code: str, message: str, *, line=None, location=None) -> None:
        self.add(ParseIssue(code, message, Severity.WARNING, line, location))
