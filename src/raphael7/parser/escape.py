r"""HL7 v2 escape sequences.

A value cannot contain a delimiter directly, so HL7 writes it as an escape
sequence between two escape characters (``\`` by default):

    \F\  field separator      \S\  component separator   \T\  subcomponent
    \R\  repetition           \E\  the escape character   \P\  truncation (v2.7)
    \Xhh..\  hexadecimal bytes                            \.br\  line break

The parsed model keeps values raw (still escaped), so a message serializes
back exactly as it was read. :func:`unescape` gives the text a raw value
stands for; :func:`escape` does the reverse.
"""

import re

from raphael7.parser.encoding import DEFAULT_ENCODING, Encoding

# Valid escapes that are not delimiters: highlighting (\H\ \N\), formatting
# (\.sp\ \.in+2\ ...), character sets (\Cxxyy\ \Mxxyyzz\) and locally
# defined escapes (\Z...\). unescape keeps these verbatim.
_OTHER_ESCAPE = re.compile(
    r"H|N|\.br|\.sp\d*|\.fi|\.nf|\.ce|\.(?:in|ti|sk)[+-]?\d+"
    r"|C[0-9A-Fa-f]{4}|M[0-9A-Fa-f]{4}(?:[0-9A-Fa-f]{2})?|Z.*"
)
_HEX = re.compile(r"X(?:[0-9A-Fa-f]{2})+")


def escape_problems(raw: str, enc: Encoding = DEFAULT_ENCODING) -> list[str]:
    r"""Describe malformed escape sequences in a raw value (empty list if none).

    The usual culprit in real feeds is an unescaped Windows path such as
    ``C:\temp``, which reads as the unknown escape ``\temp\``.
    """
    esc = enc.escape
    if esc is None or esc not in raw:
        return []

    problems = []
    start = raw.find(esc)
    while start != -1:
        end = raw.find(esc, start + 1)
        if end == -1:
            problems.append(f"unterminated escape sequence at position {start}")
            break
        code = raw[start + 1 : end]
        if not _is_valid_escape(code, enc):
            problems.append(f"unknown escape sequence {esc}{code}{esc}")
        start = raw.find(esc, end + 1)
    return problems


def unescape(raw: str, enc: Encoding = DEFAULT_ENCODING) -> str:
    r"""Return the text a raw value stands for.

    Delimiter escapes and ``\Xhh\`` become characters, and ``\.br\`` becomes
    a newline. Other valid escapes and malformed ones are kept verbatim.
    """
    esc = enc.escape
    if esc is None or esc not in raw:
        return raw

    out = []
    pos = 0
    while True:
        start = raw.find(esc, pos)
        end = raw.find(esc, start + 1) if start != -1 else -1
        if end == -1:  # no more complete escape sequences
            out.append(raw[pos:])
            break
        out.append(raw[pos:start])
        out.append(_decode_escape(raw[start + 1 : end], raw[start : end + 1], enc))
        pos = end + 1
    return "".join(out)


def escape(text: str, enc: Encoding = DEFAULT_ENCODING) -> str:
    r"""Turn text into a raw value that is safe to put in a message.

    Delimiters are escaped, ``\n`` becomes ``\.br\`` and ``\r`` becomes
    ``\X0D\``, so that ``unescape(escape(text)) == text``.
    """
    esc = enc.escape
    if esc is None:
        if any(char in text for char in (*enc.delimiters, "\r", "\n")):
            raise ValueError("cannot escape delimiters: the encoding has no escape character")
        return text

    replacements = {
        esc: f"{esc}E{esc}",
        enc.field: f"{esc}F{esc}",
        enc.component: f"{esc}S{esc}",
        "\n": f"{esc}.br{esc}",
        "\r": f"{esc}X0D{esc}",
    }
    if enc.repetition:
        replacements[enc.repetition] = f"{esc}R{esc}"
    if enc.subcomponent:
        replacements[enc.subcomponent] = f"{esc}T{esc}"
    if enc.truncation:
        replacements[enc.truncation] = f"{esc}P{esc}"

    return "".join(replacements.get(char, char) for char in text)


def _delimiter_for(code: str, enc: Encoding) -> str | None:
    """The delimiter a one-letter escape code stands for (F, S, T, R, E, P)."""
    by_code = {
        "F": enc.field,
        "S": enc.component,
        "T": enc.subcomponent,
        "R": enc.repetition,
        "E": enc.escape,
        "P": enc.truncation,
    }
    return by_code.get(code)


def _is_valid_escape(code: str, enc: Encoding) -> bool:
    if len(code) == 1 and _delimiter_for(code, enc) is not None:
        return True
    return bool(_HEX.fullmatch(code) or _OTHER_ESCAPE.fullmatch(code))


def _decode_escape(code: str, original: str, enc: Encoding) -> str:
    """What one escape sequence (``code`` without the escape characters) stands for."""
    if len(code) == 1:
        delimiter = _delimiter_for(code, enc)
        if delimiter is not None:
            return delimiter
    if _HEX.fullmatch(code):
        data = bytes.fromhex(code[1:])
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")
    if code == ".br":
        return "\n"
    return original
