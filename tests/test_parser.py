import pytest

from raphael7.parser import (
    Encoding,
    ParseError,
    Severity,
    escape,
    parse,
    parse_file,
    parse_message,
    serialize,
    unescape,
)

ADT = (
    "MSH|^~\\&|SENDER|FAC|RECV|FAC|20261123120000||ADT^A01^ADT_A01|MSG001|P|2.5.1\r"
    "EVN|A01|20261123120000\r"
    "PID|1||123456^^^HOSP^MR~987654321^^^MOH^NI||Cohen^Dana^^^Ms||19800101|F\r"
    "PV1|1|I|WARD1^101^A\r"
)


def codes(issues):
    return [i.code for i in issues]


# --- tokenizing ---------------------------------------------------------------


def test_basic_structure():
    msg = parse_message(ADT)
    assert [s.id for s in msg.segments] == ["MSH", "EVN", "PID", "PV1"]
    assert msg.issues == ()
    assert msg.message_type == "ADT^A01"
    assert msg.version == "2.5.1"
    assert msg.control_id == "MSG001"


def test_msh_field_numbering():
    msg = parse_message(ADT)
    assert msg.get("MSH-1") == "|"
    assert msg.get("MSH-2") == "^~\\&"
    assert msg.get("MSH-3") == "SENDER"
    assert msg.get("MSH-9.3") == "ADT_A01"


def test_repetitions_components_subcomponents():
    msg = parse_message(ADT.replace("HOSP^MR", "HOSP&1.2.3&ISO^MR"))
    assert msg.get("PID-3") == "123456^^^HOSP&1.2.3&ISO^MR"
    assert msg.get("PID-3[2]") == "987654321^^^MOH^NI"
    assert msg.get("PID-3[2].5") == "NI"
    assert msg.get("PID-3.4") == "HOSP&1.2.3&ISO"
    assert msg.get("PID-3.4.2") == "1.2.3"
    assert msg.get("PID-5.2") == "Dana"


def test_missing_vs_empty():
    msg = parse_message(ADT)
    assert msg.get("PID-2") == ""
    assert msg.get("PID-30") is None
    assert msg.get("PID-3[3]") is None
    assert msg.get("PID-5.9") is None
    assert msg.get("OBX-1") is None


def test_segment_occurrence():
    msg = parse_message(ADT + "OBX|1|ST|A\rOBX|2|ST|B\r")
    assert msg.get("OBX(2)-3") == "B"
    assert msg.get("OBX(3)-3") is None


def test_invalid_path():
    with pytest.raises(ValueError):
        parse_message(ADT).get("pid5")


def test_custom_encoding_characters():
    text = ADT.replace("|", "#").replace("^~\\&", "$*/!").replace("^", "$").replace("~", "*")
    msg = parse_message(text)
    assert msg.encoding == Encoding("#", "$", "*", "/", "!")
    assert msg.get("PID-3[2].5") == "NI"
    assert msg.get("MSH-2") == "$*/!"
    assert msg.issues == ()


def test_short_encoding_is_a_warning():
    msg = parse_message("MSH|^~\\|A|B\rPID|1|a&b\r")
    assert codes(msg.issues) == ["short-encoding"]
    assert msg.encoding.subcomponent is None
    assert msg.get("PID-2") == "a&b"  # not split


def test_truncation_character_v27():
    msg = parse_message("MSH|^~\\&#|A\rPID|1|ab\\P\\c\r")
    assert msg.encoding.truncation == "#"
    assert msg.value("PID-2") == "ab#c"
    assert msg.issues == ()


def test_bad_encoding():
    with pytest.raises(ParseError, match="bad-encoding"):
        parse_message("MSH|^^\\&|A\r", strict=True)
    msg = parse_message("MSH|^^\\&|A\r")
    assert "bad-encoding" in codes(msg.issues)


# --- escapes ------------------------------------------------------------------


def test_unescape_delimiters_and_hex():
    enc = Encoding()
    assert unescape(r"A\F\B\S\C\T\D\R\E\E\F", enc) == "A|B^C&D~E\\F"
    assert unescape("\\X41\\\\XC3A9\\", enc) == "Aé"
    assert unescape(r"line1\.br\line2", enc) == "line1\nline2"
    assert unescape("\\H\\bold\\N\\", enc) == "\\H\\bold\\N\\"  # kept verbatim


def test_unescape_keeps_malformed():
    assert unescape(r"C:\temp", Encoding()) == r"C:\temp"


def test_escape_round_trip():
    enc = Encoding()
    text = "a|b^c~d\\e&f\ng\rh \\H\\"
    assert unescape(escape(text, enc), enc) == text


def test_bad_escape_is_warning_even_in_strict():
    msg = parse_message("MSH|^~\\&|A\rNTE|1||see C:\\temp\\file\r", strict=True)
    assert codes(msg.issues) == ["bad-escape"]
    assert msg.issues[0].location == "NTE-3"
    msg = parse_message("MSH|^~\\&|A\rNTE|1||open \\F\r")
    assert "unterminated" in msg.issues[0].message


def test_value_decodes():
    msg = parse_message("MSH|^~\\&|A\rNTE|1||a\\F\\b\r")
    assert msg.get("NTE-3") == "a\\F\\b"
    assert msg.value("NTE-3") == "a|b"


# --- terminators, framing, batches -----------------------------------------------


@pytest.mark.parametrize("term", ["\r", "\n", "\r\n"])
def test_terminators(term):
    msg = parse_message(ADT.replace("\r", term))
    assert [s.id for s in msg.segments] == ["MSH", "EVN", "PID", "PV1"]
    expected = [] if term == "\r" else ["terminator"]
    assert codes(msg.issues) == expected


def test_mixed_terminators():
    msg = parse_message(ADT.replace("\r", "\n", 1))
    assert codes(msg.issues) == ["mixed-terminators"]


def test_no_final_terminator_and_blank_lines():
    msg = parse_message("\r\n" + ADT.rstrip("\r") + "\r\r")
    assert len(msg.segments) == 4
    assert msg.issues == ()


def test_mllp_framing():
    framed = "\x0b" + ADT + "\x1c\r" + "\x0b" + ADT.replace("MSG001", "MSG002") + "\x1c\r"
    result = parse(framed)
    assert [m.control_id for m in result.messages] == ["MSG001", "MSG002"]
    assert result.issues == []


def test_unbalanced_mllp():
    result = parse("\x0b" + ADT)
    assert codes(result.issues) == ["mllp"]
    assert len(result.messages) == 1


def test_batch_file():
    text = (
        "FHS|^~\\&|SENDER\r"
        "BHS|^~\\&|SENDER\r" + ADT + ADT.replace("MSG001", "MSG002") + "BTS|2\r"
        "FTS|1\r"
    )
    result = parse(text)
    assert [m.control_id for m in result.messages] == ["MSG001", "MSG002"]
    assert [s.id for s in result.envelope] == ["FHS", "BHS", "BTS", "FTS"]
    assert result.issues == []
    # envelope segments are not part of any message
    assert all(s.id not in {"BTS", "FTS"} for m in result.messages for s in m.segments)


def test_batch_count_mismatch():
    result = parse("BHS|^~\\&|S\r" + ADT + "BTS|3\r")
    assert codes(result.issues) == ["batch-count"]


def test_back_to_back_messages():
    result = parse(ADT + ADT.replace("MSG001", "MSG002"))
    assert len(result.messages) == 2


def test_parse_message_rejects_several():
    two = ADT + ADT
    with pytest.raises(ParseError, match="multiple-messages"):
        parse_message(two, strict=True)
    assert "multiple-messages" in codes(parse_message(two).issues)


# --- strict vs tolerant -----------------------------------------------------------


def test_text_before_msh():
    text = "garbage line\r" + ADT
    with pytest.raises(ParseError, match="text-before-msh"):
        parse(text, strict=True)
    result = parse(text)
    assert codes(result.issues) == ["text-before-msh"]
    assert len(result.messages) == 1


def test_bad_segment_id():
    text = ADT + "pid|lowercase\r"
    with pytest.raises(ParseError, match="bad-segment-id"):
        parse_message(text, strict=True)
    msg = parse_message(text)
    assert codes(msg.issues) == ["bad-segment-id"]
    assert msg.issues[0].line == 5
    assert msg.issues[0].severity is Severity.ERROR
    assert msg.segments[-1].id == "pid"


def test_empty_and_no_msh():
    with pytest.raises(ParseError, match="empty"):
        parse_message("   \r\n")
    assert codes(parse("PID|1\r").issues) == ["text-before-msh", "no-msh"]


# --- bytes and files ------------------------------------------------------------


def test_bytes_msh18_hebrew(tmp_path):
    text = ADT.replace("|P|2.5.1", "|P|2.5.1||||||8859/8").replace("Cohen", "כהן")
    path = tmp_path / "msg.hl7"
    path.write_bytes(text.encode("iso-8859-8"))
    [msg] = parse_file(path).messages
    assert msg.get("PID-5.1") == "כהן"
    assert msg.issues == ()


def test_batch_file_charset_from_first_msh():
    """FHS and BHS have no charset field: MSH-18 of the first message counts."""
    message = ADT.replace("|P|2.5.1", "|P|2.5.1||||||8859/8").replace("Cohen", "כהן")
    batch = "FHS|^~\\&|LAB\rBHS|^~\\&|LAB\r" + message + "BTS|1\rFTS|1\r"
    result = parse(batch.encode("iso-8859-8"))
    assert result.issues == []
    assert result.messages[0].get("PID-5.1") == "כהן"


def test_bytes_latin1_fallback():
    data = ADT.replace("Dana", "Dané").encode("latin-1")
    result = parse(data)
    assert codes(result.issues) == ["decode"]
    assert result.messages[0].get("PID-5.2") == "Dané"
    assert "decode" in codes(result.messages[0].issues)


def test_utf8_bom():
    msg = parse_message(b"\xef\xbb\xbf" + ADT.encode())
    assert msg.segments[0].id == "MSH"


# --- serializer -----------------------------------------------------------------


def test_serialize_is_exact():
    assert serialize(parse_message(ADT)) == ADT


def test_serialize_preserves_trailing_delimiters():
    text = "MSH|^~\\&|A|\rPID|1|a^^~|\rZZ1\r"
    assert serialize(parse_message(text)) == text
