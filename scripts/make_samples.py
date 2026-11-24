"""Generate the synthetic sample corpus in samples/.

Run:  uv run python scripts/make_samples.py

Three made-up "vendors" send ADT, ORU and ORM messages, each with habits
real feeds have (listed in samples/MANIFEST.md). A fixed seed makes every
run produce the same bytes, so a test can check the committed files.

Every patient is invented. Their teudat zehut (Israeli ID) numbers are
generated with a wrong check digit, so none can belong to a real person.

The generator works on positions only (PID-3, OBX-5), like the rest of
Raphael7: it needs no structure definitions for any HL7 version.
"""

# Hebrew names and places are intended; RUF001 would flag Hebrew letters
# as look-alikes of Latin ones.
# ruff: noqa: RUF001

import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from raphael7.parser import Encoding, escape

SEED = 7
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
GENERATED_DIRS = ("vendor-a", "vendor-b", "vendor-c", "broken")
EXPECTED_ISSUES_FILE = "expected-issues.json"

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\r"


# --- Made-up reference data -------------------------------------------------


@dataclass(frozen=True)
class Name:
    latin: str
    hebrew: str


FEMALE_NAMES = [
    Name("Noa", "נועה"),
    Name("Yael", "יעל"),
    Name("Tamar", "תמר"),
    Name("Maya", "מאיה"),
    Name("Shira", "שירה"),
    Name("Dana", "דנה"),
    Name("Rivka", "רבקה"),
    Name("Miriam", "מרים"),
    Name("Hila", "הילה"),
]
MALE_NAMES = [
    Name("Avi", "אבי"),
    Name("Yossi", "יוסי"),
    Name("Eitan", "איתן"),
    Name("Omer", "עומר"),
    Name("Daniel", "דניאל"),
    Name("Moshe", "משה"),
    Name("David", "דוד"),
    Name("Yonatan", "יונתן"),
    Name("Noam", "נועם"),
]
FAMILY_NAMES = [
    Name("Levi", "לוי"),
    Name("Cohen", "כהן"),
    Name("Mizrahi", "מזרחי"),
    Name("Peretz", "פרץ"),
    Name("Biton", "ביטון"),
    Name("Dahan", "דהן"),
    Name("Friedman", "פרידמן"),
    Name("Azoulay", "אזולאי"),
    Name("Katz", "כץ"),
    Name("Hadad", "חדד"),
    Name("Shapiro", "שפירו"),
    Name("Golan", "גולן"),
    Name("Segal", "סגל"),
    Name("Ben David", "בן דוד"),
]
CITIES = [
    Name("Haifa", "חיפה"),
    Name("Tel Aviv-Yafo", "תל אביב-יפו"),
    Name("Jerusalem", "ירושלים"),
    Name("Beer Sheva", "באר שבע"),
    Name("Netanya", "נתניה"),
    Name("Ashdod", "אשדוד"),
]
STREETS = [
    Name("Herzl", "הרצל"),
    Name("Ben Gurion", "בן גוריון"),
    Name("Weizmann", "ויצמן"),
    Name("Rothschild", "רוטשילד"),
    Name("HaNasi", "הנשיא"),
]


@dataclass(frozen=True)
class Hmo:
    """A health fund (kupat holim). The codes are made up per vendor."""

    letter_code: str  # vendor A
    number_code: str  # vendor B
    name: Name


HMOS = [
    Hmo("CLL", "1", Name("Clalit", "כללית")),
    Hmo("MAC", "2", Name("Maccabi", "מכבי")),
    Hmo("MEU", "3", Name("Meuhedet", "מאוחדת")),
    Hmo("LEU", "4", Name("Leumit", "לאומית")),
]


@dataclass(frozen=True)
class Ward:
    code: str
    service: str  # PV1-10 hospital service
    patient_class: str  # PV1-2: I inpatient, E emergency


WARDS = [
    Ward("INT-A", "MED", "I"),
    Ward("INT-B", "MED", "I"),
    Ward("SURG", "SUR", "I"),
    Ward("PED", "PED", "I"),
    Ward("ER", "EMR", "E"),
]


@dataclass(frozen=True)
class LabTest:
    loinc: str
    loinc_text: str
    local_code: str  # vendor B sends only local codes
    units: str
    low: float
    high: float


@dataclass(frozen=True)
class Panel:
    loinc: str
    loinc_text: str
    local_code: str
    tests: tuple[LabTest, ...]


CBC = Panel(
    "58410-2",
    "CBC panel - Blood by Automated count",
    "CBC",
    (
        LabTest("6690-2", "Leukocytes [#/volume] in Blood", "WBC", "10*3/uL", 4.5, 11.0),
        LabTest("718-7", "Hemoglobin [Mass/volume] in Blood", "HGB", "g/dL", 12.0, 16.0),
        LabTest("777-3", "Platelets [#/volume] in Blood", "PLT", "10*3/uL", 150.0, 400.0),
    ),
)
BMP = Panel(
    "51990-0",
    "Basic metabolic panel - Blood",
    "BMP",
    (
        LabTest("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "GLU", "mg/dL", 70.0, 99.0),
        LabTest("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "NA", "mmol/L", 135.0, 145.0),
        LabTest("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "K", "mmol/L", 3.5, 5.1),
        LabTest(
            "2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "CREAT", "mg/dL", 0.6, 1.3
        ),
    ),
)

# Vendor C adds a free-text interpretation as one OBX-5 with several repeats.
INTERPRETATION_LINES = (
    "התוצאות נבדקו",
    "אין ערכים קריטיים",
    "מומלץ לחזור על הבדיקה בעוד 3 חודשים",
)
# Vendor B adds a lab comment in NTE; the & must be escaped as \T\.
HEMOLYSIS_NOTE = "Sample slightly hemolysed; Na & K may be affected"


# --- Vendors ------------------------------------------------------------------


@dataclass(frozen=True)
class Vendor:
    """One made-up sending system and its habits (see samples/MANIFEST.md)."""

    folder: str
    sending_app: str
    facility: str
    version: str  # MSH-12
    repetition: str  # second character of MSH-2
    terminator: str  # segment terminator
    charset: str  # Python codec for the file bytes
    msh18: str  # MSH-18 character set, "" when not sent
    hebrew: bool  # names and addresses in Hebrew
    time_format: str  # timestamp precision differs per vendor
    mrn_prefix: str
    start: datetime

    @property
    def msh2(self) -> str:
        return f"^{self.repetition}\\&"

    @property
    def encoding(self) -> Encoding:
        return Encoding(component="^", repetition=self.repetition, escape="\\", subcomponent="&")


VENDOR_A = Vendor(
    folder="vendor-a",
    sending_app="ADMITPRO",
    facility="HOSP_NORTH",
    version="2.5",
    repetition="~",
    terminator="\r",
    charset="ascii",
    msh18="",
    hebrew=False,
    time_format="%Y%m%d%H%M",
    mrn_prefix="N",
    start=datetime(2026, 11, 2, 7, 0),
)
VENDOR_B = Vendor(
    folder="vendor-b",
    sending_app="MEDIX",
    facility="HOSP_SOUTH",
    version="2.3.1",
    repetition="~",
    terminator="\n",
    charset="utf-8",
    msh18="UNICODE UTF-8",
    hebrew=True,
    time_format="%Y%m%d%H%M%S",
    mrn_prefix="",
    start=datetime(2026, 11, 2, 6, 30),
)
VENDOR_C = Vendor(
    folder="vendor-c",
    sending_app="OLDHIS",
    facility="HOSP_EAST",
    version="2.4",
    repetition="!",
    terminator="\r",
    charset="iso-8859-8",
    msh18="8859/8",
    hebrew=True,
    time_format="%Y%m%d%H%M",
    mrn_prefix="E",
    start=datetime(2026, 11, 2, 8, 15),
)

# Vendor B was upgraded to 2.5 on some interfaces: every 7th message says 2.5
# and moves the national ID from PID-2 to PID-3, like a real upgrade does.
VENDOR_B_DRIFT_EVERY = 7


# --- Synthetic patients and visits -------------------------------------------


@dataclass(frozen=True)
class Patient:
    national_id: str  # teudat zehut with a wrong check digit, a placeholder, or ""
    mrn: str
    family: Name
    given: Name
    sex: str
    birth_date: str
    street: Name
    house_number: int
    city: Name
    zip_code: str
    phone: str
    hmo: Hmo
    other_ids: tuple[str, ...] = ()  # extra PID-3 repeats (CX values) from other systems


@dataclass(frozen=True)
class Doctor:
    id: str
    family: Name
    given: Name


@dataclass(frozen=True)
class Visit:
    number: str
    patient: Patient
    ward: Ward
    room: str
    bed: str
    doctor: Doctor
    admitted: datetime
    discharged: datetime


@dataclass(frozen=True)
class Order:
    number: str
    visit: Visit
    panel: Panel


@dataclass(frozen=True)
class Event:
    """One message to send: what happened, when, for which visit."""

    time: datetime
    kind: str  # "A01", "A08", "A03", "ORM" or "ORU"
    visit: Visit
    order: Order | None = None


def israeli_id_check_digit(first_eight: str) -> int:
    """The check digit that would make a teudat zehut valid.

    Digits are weighted 1, 2, 1, 2, ...; a two-digit product counts as the
    sum of its digits; the total of all nine digits must end in 0.
    """
    total = 0
    for index, char in enumerate(first_eight):
        product = int(char) * (1 if index % 2 == 0 else 2)
        if product > 9:
            product -= 9
        total += product
    return (10 - total % 10) % 10


def is_valid_israeli_id(number: str) -> bool:
    """True when the 9-digit number passes the teudat zehut check."""
    if len(number) != 9 or not number.isdigit():
        return False
    return israeli_id_check_digit(number[:8]) == int(number[8])


def fake_israeli_id(rng: random.Random) -> str:
    """A 9-digit ID that fails the check digit, so it is nobody's real ID."""
    first_eight = f"{rng.randint(0, 99_999_999):08d}"
    valid_digit = israeli_id_check_digit(first_eight)
    wrong_digit = (valid_digit + rng.randint(1, 9)) % 10
    return first_eight + str(wrong_digit)


# Placeholder used when the ID is unknown (newborn, tourist, unconscious patient).
# It passes the check digit, and every patient who gets it looks like the same person.
PLACEHOLDER_ID = "000000000"

# Made-up codes of older systems whose patient IDs were merged into one PID-3.
LEGACY_SYSTEMS = (
    "LAB1", "LAB2", "RAD", "PHARM", "CARD", "ONC", "ER", "ICU", "DIAL",
    "PATH", "BB", "NICU", "OBGYN", "ORTHO", "PSY", "REHAB", "DERM", "ENT",
)  # fmt: skip


def national_id_for(vendor: Vendor, index: int, generated: str) -> str:
    """The ID quality problems real feeds have.

    A: no national ID for patients 5 and 11 (empty, not even a placeholder).
    B: the placeholder 000000000 for patients 2, 6 and 10.
    """
    if vendor is VENDOR_A and index % 6 == 5:
        return ""
    if vendor is VENDOR_B and index % 4 == 2:
        return PLACEHOLDER_ID
    return generated


def legacy_ids(vendor: Vendor, index: int) -> tuple[str, ...]:
    """C: patient 7 carries 18 IDs from older systems, 20 PID-3 repeats in all.

    A separate random generator keeps the other patients' data unchanged.
    """
    if vendor is not VENDOR_C or index != 7:
        return ()
    rng = random.Random(SEED + index)
    ids = []
    for system in LEGACY_SYSTEMS:
        ids.append(f"{rng.randint(10_000, 9_999_999)}^^^{system}^PI")
    return tuple(ids)


def make_patient(rng: random.Random, vendor: Vendor, index: int) -> Patient:
    sex = rng.choice(["F", "M"])
    given_names = FEMALE_NAMES if sex == "F" else MALE_NAMES
    birth = datetime(1940, 1, 1) + timedelta(days=rng.randint(0, 30_000))
    return Patient(
        national_id=national_id_for(vendor, index, fake_israeli_id(rng)),
        mrn=f"{vendor.mrn_prefix}{rng.randint(100_000, 999_999)}",
        family=rng.choice(FAMILY_NAMES),
        given=rng.choice(given_names),
        sex=sex,
        birth_date=birth.strftime("%Y%m%d"),
        street=rng.choice(STREETS),
        house_number=rng.randint(1, 120),
        city=rng.choice(CITIES),
        zip_code=f"{rng.randint(1_000_000, 9_999_999)}",
        phone=f"05{rng.randint(0, 8)}-{rng.randint(1_000_000, 9_999_999)}",
        hmo=rng.choice(HMOS),
        other_ids=legacy_ids(vendor, index),
    )


def make_doctor(rng: random.Random) -> Doctor:
    given_names = rng.choice([FEMALE_NAMES, MALE_NAMES])
    return Doctor(
        id=f"D{rng.randint(1000, 9999)}",
        family=rng.choice(FAMILY_NAMES),
        given=rng.choice(given_names),
    )


VISITS_PER_VENDOR = 12


def make_events(rng: random.Random, vendor: Vendor) -> list[Event]:
    """60 messages per vendor: 12 admissions, their updates, discharges, orders and results.

    Visit i gets an A08 unless i % 4 == 3 and an A03 unless i % 4 == 0 (still
    in hospital). The first 10 visits get a CBC order with its result, plus a
    BMP result later in the stay.
    """
    doctors = []
    for _ in range(4):
        doctors.append(make_doctor(rng))

    events = []
    for i in range(VISITS_PER_VENDOR):
        ward = rng.choice(WARDS)
        admitted = vendor.start + timedelta(hours=5 * i, minutes=rng.randint(0, 59))
        stay = timedelta(days=rng.randint(1, 4), hours=rng.randint(0, 12))
        visit = Visit(
            number=f"V{rng.randint(10_000_000, 99_999_999)}",
            patient=make_patient(rng, vendor, i),
            ward=ward,
            room=str(rng.randint(1, 30)),
            bed=rng.choice(["A", "B", "C"]),
            doctor=rng.choice(doctors),
            admitted=admitted,
            discharged=admitted + stay,
        )
        events.append(Event(admitted, "A01", visit))
        if i % 4 != 3:
            events.append(Event(admitted + timedelta(hours=2), "A08", visit))
        if i % 4 != 0:
            events.append(Event(visit.discharged, "A03", visit))
        if i < 10:
            cbc_order = Order(f"ORD{rng.randint(100_000, 999_999)}", visit, CBC)
            bmp_order = Order(f"ORD{rng.randint(100_000, 999_999)}", visit, BMP)
            events.append(Event(admitted + timedelta(hours=1), "ORM", visit, cbc_order))
            events.append(Event(admitted + timedelta(hours=3), "ORU", visit, cbc_order))
            events.append(Event(admitted + timedelta(hours=20), "ORU", visit, bmp_order))

    events.sort(key=lambda event: event.time)
    return events


# --- Building segments ----------------------------------------------------------


def segment(seg_id: str, fields: dict[int, str]) -> str:
    """One segment line from {field number: raw value}; missing fields stay empty."""
    parts = [seg_id]
    for number in range(1, max(fields) + 1):
        parts.append(fields.get(number, ""))
    return "|".join(parts)


def text(vendor: Vendor, name: Name) -> str:
    """A name or place in the vendor's language, escaped for its delimiters."""
    value = name.hebrew if vendor.hebrew else name.latin
    return escape(value, vendor.encoding)


@dataclass(frozen=True)
class MessageHeader:
    """What changes per message in MSH."""

    time: datetime
    message_type: str  # "ADT", "ORU", "ORM"
    trigger: str  # "A01", "R01", ...
    structure: str  # "ADT_A01", ...
    control_id: str
    version: str


def msh(vendor: Vendor, header: MessageHeader) -> str:
    """MSH is written by hand: MSH-1 is the separator and MSH-2 must not be escaped."""
    if header.version == "2.3.1":
        msh9 = f"{header.message_type}^{header.trigger}"  # 2.3.1 has no message structure
    else:
        msh9 = f"{header.message_type}^{header.trigger}^{header.structure}"
    fields = {
        3: vendor.sending_app,
        4: vendor.facility,
        5: "RAPHAEL7",
        6: "INTEG",
        7: header.time.strftime(vendor.time_format),
        9: msh9,
        10: header.control_id,
        11: "P",
        12: header.version,
    }
    if vendor.msh18:
        fields[18] = vendor.msh18
    rest = segment("MSH", fields).removeprefix("MSH|||")  # drop the placeholders for MSH-1/2
    return f"MSH|{vendor.msh2}|{rest}"


def evn(vendor: Vendor, trigger: str, time: datetime) -> str:
    """EVN-1 (event type) was deprecated in 2.5; vendors A and C still fill it."""
    fields = {2: time.strftime(vendor.time_format)}
    if vendor is not VENDOR_B:
        fields[1] = trigger
    return segment("EVN", fields)


def pid(vendor: Vendor, visit: Visit, version: str) -> str:
    """Where the national ID goes differs per vendor (the "moved field" variation).

    A and C: PID-3 holds the national ID and the MRN as two repeats.
    B on 2.3.1: national ID alone in PID-2 (external ID), MRN in PID-3, and
    the visit number in PID-18 (account number) instead of PV1-19.
    A patient without a national ID has only the MRN (plus any legacy IDs).
    """
    patient = visit.patient
    mrn = f"{patient.mrn}^^^{vendor.facility}^MR"
    identifiers = []
    if patient.national_id:
        identifiers.append(f"{patient.national_id}^^^MOI^NNISR")
    identifiers.append(mrn)
    identifiers.extend(patient.other_ids)
    fields = {
        1: "1",
        5: f"{text(vendor, patient.family)}^{text(vendor, patient.given)}",
        7: patient.birth_date,
        8: patient.sex,
        11: (
            f"{text(vendor, patient.street)} {patient.house_number}"
            f"^^{text(vendor, patient.city)}^^{patient.zip_code}^ISR"
        ),
        13: patient.phone if vendor is VENDOR_A else patient.phone.replace("-", ""),
    }
    if vendor is VENDOR_B and version == "2.3.1":
        fields[2] = patient.national_id
        fields[3] = mrn
    else:
        fields[3] = vendor.repetition.join(identifiers)
    if vendor is VENDOR_B:
        fields[18] = visit.number
    return segment("PID", fields)


def pv1(vendor: Vendor, visit: Visit, discharged: bool) -> str:
    """Vendor C sends the HMO in PV1-20 (financial class); B leaves PV1-19 empty."""
    doctor = visit.doctor
    fields = {
        1: "1",
        2: visit.ward.patient_class,
        3: f"{visit.ward.code}^{visit.room}^{visit.bed}^{vendor.facility}",
        7: f"{doctor.id}^{text(vendor, doctor.family)}^{text(vendor, doctor.given)}",
        10: visit.ward.service,
        44: visit.admitted.strftime(vendor.time_format),
    }
    if vendor is not VENDOR_B:
        fields[19] = visit.number
    if vendor is VENDOR_C:
        fields[20] = visit.patient.hmo.number_code
    if discharged:
        fields[45] = visit.discharged.strftime(vendor.time_format)
    return segment("PV1", fields)


def hmo_segment(vendor: Vendor, patient: Patient) -> str | None:
    """Vendor A sends the HMO in IN1; vendor B in its own Z-segment ZPI."""
    hmo = patient.hmo
    if vendor is VENDOR_A:
        return segment("IN1", {1: "1", 2: "BASIC", 3: hmo.letter_code, 4: text(vendor, hmo.name)})
    if vendor is VENDOR_B:
        return segment("ZPI", {1: "1", 2: hmo.number_code, 3: text(vendor, hmo.name)})
    return None


def panel_code(vendor: Vendor, panel: Panel) -> str:
    """A: LOINC. B: local code only. C: LOINC with the local code as alternate."""
    if vendor is VENDOR_B:
        return f"{panel.local_code}^{panel.local_code}^L"
    if vendor is VENDOR_C:
        return f"{panel.loinc}^{panel.loinc_text}^LN^{panel.local_code}^^L"
    return f"{panel.loinc}^{panel.loinc_text}^LN"


def test_code(vendor: Vendor, test: LabTest) -> str:
    if vendor is VENDOR_B:
        return f"{test.local_code}^{test.local_code}^L"
    if vendor is VENDOR_C:
        return f"{test.loinc}^{test.loinc_text}^LN^{test.local_code}^^L"
    return f"{test.loinc}^{test.loinc_text}^LN"


def doctor_xcn(vendor: Vendor, doctor: Doctor) -> str:
    return f"{doctor.id}^{text(vendor, doctor.family)}^{text(vendor, doctor.given)}"


def orc(vendor: Vendor, order: Order, control: str, time: datetime) -> str:
    """Vendor B leaves ORC-12 (ordering provider) empty and only fills OBR-16."""
    fields = {1: control, 2: order.number, 9: time.strftime(vendor.time_format)}
    if vendor is not VENDOR_B:
        fields[12] = doctor_xcn(vendor, order.visit.doctor)
    return segment("ORC", fields)


def obr(vendor: Vendor, order: Order, time: datetime, resulted: bool) -> str:
    fields = {
        1: "1",
        2: order.number,
        4: panel_code(vendor, order.panel),
        7: time.strftime(vendor.time_format),
        16: doctor_xcn(vendor, order.visit.doctor),
    }
    if resulted:
        fields[3] = f"F{order.number[3:]}"  # filler order number from the lab
        fields[25] = "F"
    return segment("OBR", fields)


def result_value(rng: random.Random, test: LabTest) -> float:
    """Mostly normal values, sometimes a little outside the reference range."""
    spread = test.high - test.low
    return rng.uniform(test.low - 0.2 * spread, test.high + 0.2 * spread)


def abnormal_flag(vendor: Vendor, test: LabTest, value: float) -> str:
    """OBX-8: H or L; vendor A writes N for normal, the others leave it empty."""
    if value > test.high:
        return "H"
    if value < test.low:
        return "L"
    return "N" if vendor is VENDOR_A else ""


def obx_segments(rng: random.Random, vendor: Vendor, order: Order, time: datetime) -> list[str]:
    lines = []
    set_id = 0
    for test in order.panel.tests:
        set_id += 1
        value = result_value(rng, test)
        fields = {
            1: str(set_id),
            2: "NM",
            3: test_code(vendor, test),
            5: f"{value:.1f}",
            6: test.units,
            7: f"{test.low}-{test.high}",
            8: abnormal_flag(vendor, test, value),
            11: "F",
            14: time.strftime(vendor.time_format),
        }
        lines.append(segment("OBX", fields))

    if vendor is VENDOR_C:
        # One text result whose lines are OBX-5 repeats (the "!" repetition character).
        escaped_lines = []
        for line in INTERPRETATION_LINES:
            escaped_lines.append(escape(line, vendor.encoding))
        set_id += 1
        fields = {
            1: str(set_id),
            2: "TX",
            3: "INTERP^Interpretation^L",
            5: vendor.repetition.join(escaped_lines),
            11: "F",
        }
        lines.append(segment("OBX", fields))
    return lines


# --- Building messages ------------------------------------------------------------

STRUCTURES = {"A01": "ADT_A01", "A08": "ADT_A01", "A03": "ADT_A03"}


def message_version(vendor: Vendor, sequence: int) -> str:
    if vendor is VENDOR_B and sequence % VENDOR_B_DRIFT_EVERY == VENDOR_B_DRIFT_EVERY - 1:
        return "2.5"
    return vendor.version


def adt_message(vendor: Vendor, event: Event, header: MessageHeader) -> list[str]:
    """Vendor C sends A08 (patient update) without PV1: a missing segment."""
    visit = event.visit
    lines = [msh(vendor, header), evn(vendor, event.kind, event.time)]
    lines.append(pid(vendor, visit, header.version))
    if not (vendor is VENDOR_C and event.kind == "A08"):
        lines.append(pv1(vendor, visit, discharged=event.kind == "A03"))
    hmo = hmo_segment(vendor, visit.patient)
    if hmo and event.kind != "A03":
        lines.append(hmo)
    return lines


def orm_message(vendor: Vendor, event: Event, header: MessageHeader) -> list[str]:
    order = event.order
    lines = [msh(vendor, header), pid(vendor, event.visit, header.version)]
    lines.append(pv1(vendor, event.visit, discharged=False))
    lines.append(orc(vendor, order, "NW", event.time))
    lines.append(obr(vendor, order, event.time, resulted=False))
    return lines


def oru_message(
    rng: random.Random, vendor: Vendor, event: Event, header: MessageHeader
) -> list[str]:
    """A: ORC before OBR. B: no ORC, plus an NTE comment. C: no PV1."""
    order = event.order
    lines = [msh(vendor, header), pid(vendor, event.visit, header.version)]
    if vendor is not VENDOR_C:
        lines.append(pv1(vendor, event.visit, discharged=False))
    if vendor is not VENDOR_B:
        lines.append(orc(vendor, order, "RE", event.time))
    lines.append(obr(vendor, order, event.time, resulted=True))
    lines.extend(obx_segments(rng, vendor, order, event.time))
    if vendor is VENDOR_B and order.panel is BMP:
        lines.append(segment("NTE", {1: "1", 2: "L", 3: escape(HEMOLYSIS_NOTE, vendor.encoding)}))
    return lines


def build_message(rng: random.Random, vendor: Vendor, event: Event, sequence: int) -> list[str]:
    version = message_version(vendor, sequence)
    control_id = f"{vendor.sending_app[:3]}{sequence + 1:06d}"
    if event.kind == "ORM":
        header = MessageHeader(event.time, "ORM", "O01", "ORM_O01", control_id, version)
        return orm_message(vendor, event, header)
    if event.kind == "ORU":
        header = MessageHeader(event.time, "ORU", "R01", "ORU_R01", control_id, version)
        return oru_message(rng, vendor, event, header)
    header = MessageHeader(
        event.time, "ADT", event.kind, STRUCTURES[event.kind], control_id, version
    )
    return adt_message(vendor, event, header)


def to_bytes(vendor: Vendor, lines: list[str]) -> bytes:
    """Every segment, including the last, ends with the vendor's terminator."""
    joined = ""
    for line in lines:
        joined += line + vendor.terminator
    return joined.encode(vendor.charset)


def file_name(sequence: int, event: Event) -> str:
    kind = "adt-" + event.kind.lower() if event.kind.startswith("A") else event.kind.lower()
    return f"{sequence + 1:04d}-{kind}.hl7"


# --- The corpus -------------------------------------------------------------------


@dataclass
class Corpus:
    files: dict[str, bytes]  # path relative to samples/ -> content
    expected_issues: dict[str, list[str]]  # path -> sorted, unique ParseIssue codes

    def add(self, path: str, content: bytes, issue_codes: list[str]) -> None:
        self.files[path] = content
        self.expected_issues[path] = sorted(set(issue_codes))


def add_one_file_per_message(rng: random.Random, vendor: Vendor, corpus: Corpus) -> None:
    """Vendors A and B: one message per file. B's \\n terminators are a warning."""
    expected = ["terminator"] if vendor.terminator == "\n" else []
    events = make_events(rng, vendor)
    for sequence, event in enumerate(events):
        lines = build_message(rng, vendor, event, sequence)
        path = f"{vendor.folder}/{file_name(sequence, event)}"
        corpus.add(path, to_bytes(vendor, lines), expected)


def add_vendor_c(rng: random.Random, corpus: Corpus) -> None:
    """Vendor C: ADT and ORM logged from the MLLP listener, still framed;
    ORU results sent once a day as a batch file (FHS/BHS ... BTS/FTS)."""
    vendor = VENDOR_C
    events = make_events(rng, vendor)
    results_by_day: dict[str, list[bytes]] = {}
    for sequence, event in enumerate(events):
        content = to_bytes(vendor, build_message(rng, vendor, event, sequence))
        if event.kind == "ORU":
            day = event.time.strftime("%Y-%m-%d")
            results_by_day.setdefault(day, []).append(content)
        else:
            path = f"{vendor.folder}/{file_name(sequence, event)}"
            corpus.add(path, MLLP_START + content + MLLP_END, [])

    for day, messages in results_by_day.items():
        batch_time = datetime.strptime(day, "%Y-%m-%d").replace(hour=23, minute=59)
        stamp = batch_time.strftime(vendor.time_format)
        sender = f"{vendor.sending_app}|{vendor.facility}"
        header_fields = f"|{vendor.msh2}|{sender}|RAPHAEL7|INTEG|{stamp}"
        lines = [f"FHS{header_fields}", f"BHS{header_fields}"]
        start = to_bytes(vendor, lines)
        end = to_bytes(vendor, [f"BTS|{len(messages)}", "FTS|1"])
        path = f"{vendor.folder}/oru-batch-{day}.hl7"
        corpus.add(path, start + b"".join(messages) + end, [])


def join(segment_lines: list[str], terminator: str = "\r") -> bytes:
    """Segment lines back to bytes, each ending with the terminator."""
    return (terminator.join(segment_lines) + terminator).encode("latin-1")


def with_wrong_batch_count(batch: bytes) -> bytes:
    """The same batch, with BTS-1 claiming one message more than it holds."""
    lines = batch.split(b"\r")
    for index, line in enumerate(lines):
        if line.startswith(b"BTS|"):
            declared = int(line.split(b"|")[1])
            lines[index] = b"BTS|" + str(declared + 1).encode()
    return b"\r".join(lines)


@dataclass(frozen=True)
class BrokenCase:
    """A hand-made broken file, the ParseIssue codes it must produce, and why."""

    name: str
    content: bytes
    issue_codes: list[str]


def broken_cases(base: str, batch: bytes) -> list[BrokenCase]:
    """Broken files made from one clean vendor A message (\\r terminated) and one batch.

    Some breakages give no ParseIssue at all (an unescaped delimiter just makes
    an extra field): the parser can't know, so `scan` must flag them by shape.
    """
    lines = base.split("\r")[:-1]  # the last element is "" after the final \r
    msh_line = lines[0]

    cases = [BrokenCase("empty.hl7", b"", ["empty"])]

    cases.append(BrokenCase("no-msh.hl7", join(lines[1:]), ["no-msh", "text-before-msh"]))

    repeated_delimiter = msh_line.replace("MSH|^~\\&|", "MSH|^~\\&^|", 1)
    cases.append(
        BrokenCase("bad-encoding.hl7", join([repeated_delimiter, *lines[1:]]), ["bad-encoding"])
    )

    short_msh2 = msh_line.replace("MSH|^~\\&|", "MSH|^~|", 1)
    cases.append(
        BrokenCase("short-encoding.hl7", join([short_msh2, *lines[1:]]), ["short-encoding"])
    )

    lowercase = []
    for line in lines:
        lowercase.append("Pid" + line[3:] if line.startswith("PID") else line)
    cases.append(BrokenCase("bad-segment-id.hl7", join(lowercase), ["bad-segment-id"]))

    windows_path = "NTE|1|L|Report saved to C:\\lab\\reports\\2026"
    cases.append(BrokenCase("bad-escape.hl7", join([*lines, windows_path]), ["bad-escape"]))

    mixed = (lines[0] + "\r" + "\r\n".join(lines[1:]) + "\r\n").encode("latin-1")
    cases.append(BrokenCase("mixed-terminators.hl7", mixed, ["mixed-terminators"]))

    cases.append(BrokenCase("mllp-unbalanced.hl7", MLLP_START + join(lines), ["mllp"]))

    # Hebrew saved as Windows-1255 with no MSH-18: not UTF-8, so it decodes as Latin-1.
    hebrew_note = "NTE|1|L|דגימה המוליטית"
    cp1255 = join(lines) + (hebrew_note + "\r").encode("cp1255")
    cases.append(BrokenCase("windows-1255-no-charset.hl7", cp1255, ["decode"]))

    cases.append(BrokenCase("batch-count.hl7", with_wrong_batch_count(batch), ["batch-count"]))

    unescaped = "NTE|1|L|Na & K low | repeat test"
    cases.append(BrokenCase("unescaped-delimiter.hl7", join([*lines, unescaped]), []))

    cut_mid_segment = join(lines)[: len(join(lines)) * 2 // 3]
    cases.append(BrokenCase("truncated.hl7", cut_mid_segment, []))
    return cases


def add_broken(corpus: Corpus) -> None:
    vendor_a_oru = next(path for path in corpus.files if "vendor-a" in path and "oru" in path)
    base = corpus.files[vendor_a_oru].decode("ascii")
    batch_path = next(path for path in corpus.files if "oru-batch" in path)
    for case in broken_cases(base, corpus.files[batch_path]):
        corpus.add(f"broken/{case.name}", case.content, case.issue_codes)


def build_corpus() -> Corpus:
    """Everything that goes in samples/, built in memory (so a test can compare)."""
    rng = random.Random(SEED)
    corpus = Corpus(files={}, expected_issues={})
    add_one_file_per_message(rng, VENDOR_A, corpus)
    add_one_file_per_message(rng, VENDOR_B, corpus)
    add_vendor_c(rng, corpus)
    add_broken(corpus)
    return corpus


def write_corpus(corpus: Corpus, root: Path) -> None:
    """Replace the generated folders; hand-written files in samples/ are left alone."""
    for folder in GENERATED_DIRS:
        shutil.rmtree(root / folder, ignore_errors=True)
    for path, content in corpus.files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    expected = json.dumps(corpus.expected_issues, indent=2, ensure_ascii=False, sort_keys=True)
    (root / EXPECTED_ISSUES_FILE).write_text(expected + "\n", encoding="utf-8")


def main() -> None:
    corpus = build_corpus()
    write_corpus(corpus, SAMPLES_DIR)
    print(f"wrote {len(corpus.files)} files to {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
