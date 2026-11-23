r"""HL7 v2 escape sequences (\F\, \S\, \T\, \R\, \E\, \P\, \Xhh\, \.br\ ...).

The parsed model keeps values raw (still escaped), so a message serializes
back exactly as it was read. Use :func:`unescape` to get the text a value
stands for, and :func:`escape` to turn text into a raw value.
"""

import re

from raphael7.parser.encoding import DEFAULT_ENCODING, Encoding

# Escapes that are valid but are not delimiters: formatting, character sets,
# highlighting and locally defined (\Z...\) escapes. Kept verbatim by unescape.
_OTHER_ESCAPE = re.compile(
    r"H|N|\.br|\.sp\d*|\.fi|\.nf|\.ce|\.(?:in|ti|sk)[+-]?\d+"
    r"|C[0-9A-Fa-f]{4}|M[0-9A-Fa-f]{4}(?:[0-9A-Fa-f]{2})?|Z.*"
)
_HEX = re.compile(r"X(?:[0-9A-Fa-f]{2})+")


def _delimiter_for(code: str, enc: Encoding) -> str | None:
    return {
        "F": enc.field,
        "S": enc.component,
        "T": enc.subcomponent,
        "R": enc.repetition,
        "E": enc.escape,
        "P": enc.truncation,
    }.get(code)


def _decode_hex(digits: str) -> str:
    data = bytes.fromhex(digits)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def escape_problems(raw: str, enc: Encoding = DEFAULT_ENCODING) -> list[str]:
    """Describe malformed escape sequences in a raw value (empty list if none)."""
    esc = enc.escape
    if esc is None or esc not in raw:
        return []
    problems = []
    i = raw.find(esc)
    while i != -1:
        j = raw.find(esc, i + 1)
        if j == -1:
            problems.append(f"unterminated escape sequence at position {i}")
            break
        code = raw[i + 1 : j]
        if not (
            (len(code) == 1 and _delimiter_for(code, enc) is not None)
            or _HEX.fullmatch(code)
            or _OTHER_ESCAPE.fullmatch(code)
        ):
            problems.append(f"unknown escape sequence {esc}{code}{esc}")
        i = raw.find(esc, j + 1)
    return problems


def unescape(raw: str, enc: Encoding = DEFAULT_ENCODING) -> str:
    r"""Return the text a raw value stands for.

    Delimiter escapes and ``\Xhh\`` become characters and ``\.br\`` becomes a
    newline. Other valid escapes (highlighting, character sets, ``\Z..\``) and
    malformed ones are kept verbatim.
    """
    esc = enc.escape
    if esc is None or esc not in raw:
        return raw
    out = []
    pos = 0
    while True:
        i = raw.find(esc, pos)
        if i == -1:
            out.append(raw[pos:])
            break
        j = raw.find(esc, i + 1)
        if j == -1:
            out.append(raw[pos:])
            break
        out.append(raw[pos:i])
        code = raw[i + 1 : j]
        delim = _delimiter_for(code, enc) if len(code) == 1 else None
        if delim is not None:
            out.append(delim)
        elif _HEX.fullmatch(code):
            out.append(_decode_hex(code[1:]))
        elif code == ".br":
            out.append("\n")
        else:
            out.append(raw[i : j + 1])
        pos = j + 1
    return "".join(out)


def escape(text: str, enc: Encoding = DEFAULT_ENCODING) -> str:
    r"""Turn text into a raw value that is safe to put in a message.

    Delimiters are escaped, ``\n`` becomes ``\.br\`` and ``\r`` becomes
    ``\X0D\``, so that ``unescape(escape(text)) == text``.
    """
    esc = enc.escape
    if esc is None:
        if any(c in text for c in (*enc.delimiters, "\r", "\n")):
            raise ValueError("cannot escape delimiters: the encoding has no escape character")
        return text
    codes = {
        enc.escape: "E",
        enc.field: "F",
        enc.component: "S",
        enc.repetition: "R",
        enc.subcomponent: "T",
        enc.truncation: "P",
    }
    codes.pop(None, None)
    out = []
    for c in text:
        if c in codes:
            out.append(f"{esc}{codes[c]}{esc}")
        elif c == "\n":
            out.append(f"{esc}.br{esc}")
        elif c == "\r":
            out.append(f"{esc}X0D{esc}")
        else:
            out.append(c)
    return "".join(out)
