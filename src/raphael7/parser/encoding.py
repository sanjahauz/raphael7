"""Delimiters ("encoding characters") declared in MSH-1 / MSH-2."""

from dataclasses import dataclass

# Segments that declare their own delimiters in field 1 and field 2.
HEADER_SEGMENTS = frozenset({"MSH", "FHS", "BHS"})


@dataclass(frozen=True, slots=True)
class Encoding:
    """The delimiters a message uses.

    Optional delimiters are ``None`` when MSH-2 does not declare them; the
    parser then does not split on them.
    """

    field: str = "|"
    component: str = "^"
    repetition: str | None = "~"
    escape: str | None = "\\"
    subcomponent: str | None = "&"
    truncation: str | None = None  # v2.7+, 5th character of MSH-2

    @property
    def msh2(self) -> str:
        """MSH-2 as it would be written for this encoding."""
        chars = [self.component, self.repetition, self.escape, self.subcomponent, self.truncation]
        out = []
        for c in chars:
            if c is None:
                break
            out.append(c)
        return "".join(out)

    @property
    def delimiters(self) -> tuple[str, ...]:
        """Every declared delimiter, including the escape and truncation characters."""
        chars = (
            self.field,
            self.component,
            self.repetition,
            self.escape,
            self.subcomponent,
            self.truncation,
        )
        return tuple(c for c in chars if c is not None)


DEFAULT_ENCODING = Encoding()


def read_header_encoding(line: str) -> tuple[Encoding, str, list[tuple[str, str, str]]]:
    """Read the delimiters from a header segment line (MSH, FHS or BHS).

    Returns ``(encoding, msh2_raw, problems)`` where each problem is
    ``(code, severity, message)``. On an unusable header the default encoding
    is returned together with an error, so tolerant parsing can continue.
    """
    problems: list[tuple[str, str, str]] = []
    if len(line) < 4:
        problems.append(("bad-encoding", "error", f"{line[:3]} has no field separator"))
        return DEFAULT_ENCODING, "", problems

    fs = line[3]
    if fs.isalnum() or fs.isspace():
        problems.append(("bad-encoding", "error", f"invalid field separator {fs!r} in MSH-1"))
        return DEFAULT_ENCODING, "", problems

    end = line.find(fs, 4)
    msh2 = line[4:] if end == -1 else line[4:end]

    if not msh2:
        problems.append(("bad-encoding", "error", "MSH-2 (encoding characters) is empty"))
        return Encoding(field=fs), msh2, problems

    if len(msh2) > 5:
        problems.append(
            ("bad-encoding", "error", f"MSH-2 has {len(msh2)} characters (at most 5 expected)")
        )
        return Encoding(field=fs), msh2, problems

    bad = [c for c in msh2 if c.isalnum() or c.isspace()]
    if bad:
        problems.append(("bad-encoding", "error", f"invalid encoding characters {msh2!r} in MSH-2"))
        return Encoding(field=fs), msh2, problems

    if len(set(msh2 + fs)) != len(msh2) + 1:
        problems.append(("bad-encoding", "error", f"MSH-1/MSH-2 repeat a delimiter: {fs + msh2!r}"))
        return Encoding(field=fs), msh2, problems

    if len(msh2) < 4:
        problems.append(
            (
                "short-encoding",
                "warning",
                f"MSH-2 declares only {len(msh2)} encoding characters ({msh2!r})",
            )
        )

    padded = list(msh2) + [None] * (5 - len(msh2))
    encoding = Encoding(
        field=fs,
        component=padded[0],
        repetition=padded[1],
        escape=padded[2],
        subcomponent=padded[3],
        truncation=padded[4],
    )
    return encoding, msh2, problems
