"""Property tests: parse(serialize(m)) == m for generated messages."""

from hypothesis import given
from hypothesis import strategies as st

from raphael7.parser import Encoding, Message, Segment, escape, parse_message, serialize, unescape

# Characters that can be delimiters (never letters, digits or whitespace).
DELIMITER_POOL = "|^~\\&#!$%*/+?@"
RESERVED = "\r\n\x0b\x1c"


@st.composite
def encodings(draw):
    chars = draw(st.permutations(DELIMITER_POOL))
    n = draw(st.integers(min_value=4, max_value=5))  # optional v2.7 truncation char
    fs, comp, rep, esc, sub, trunc = chars[:6]
    return Encoding(fs, comp, rep, esc, sub, trunc if n == 5 else None)


def leaf(enc: Encoding):
    banned = set(enc.delimiters) - {enc.escape, enc.truncation} | set(RESERVED)
    return st.text(
        st.characters(codec="utf-8", exclude_characters=banned, exclude_categories=["Cs"]),
        max_size=6,
    )


def fields(enc: Encoding):
    comp = st.lists(leaf(enc), min_size=1, max_size=3).map(tuple)
    rep = st.lists(comp, min_size=1, max_size=3).map(tuple)
    return st.lists(rep, min_size=1, max_size=3).map(tuple)


segment_ids = st.from_regex(r"\A[A-Z][A-Z0-9]{2}\Z").filter(
    lambda s: s not in {"MSH", "FHS", "BHS", "BTS", "FTS"}
)


@st.composite
def messages(draw):
    enc = draw(encodings())
    header = (
        (((enc.field,),),),
        (((enc.msh2,),),),
        *draw(st.lists(fields(enc), max_size=12)),
    )
    body = draw(
        st.lists(
            st.builds(Segment, segment_ids, st.lists(fields(enc), max_size=8).map(tuple)),
            max_size=6,
        )
    )
    return Message((Segment("MSH", header), *body), enc)


@given(messages(), st.sampled_from(["\r", "\n", "\r\n"]))
def test_parse_serialize_round_trip(msg, terminator):
    text = serialize(msg, terminator)
    assert parse_message(text) == msg
    # and the text itself round-trips exactly with the standard terminator
    assert serialize(parse_message(text)) == serialize(msg)


@given(encodings(), st.text(st.characters(exclude_categories=["Cs"])))
def test_escape_round_trip(enc, text):
    raw = escape(text, enc)
    assert not any(c in raw for c in set(enc.delimiters) - {enc.escape})
    assert unescape(raw, enc) == text
