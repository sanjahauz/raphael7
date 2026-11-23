# Raphael7 — Project Plan

*Raphael7* (as in HL7): heals messy real-world HL7 v2 feeds into clean FHIR.

Last updated: 2026-11-23

---

## 1. One-liner

A Python command-line tool that **scans a real HL7 v2 message feed, finds the variations and outliers, turns chosen messages into regression tests, and checks the HL7 v2 → FHIR R4 (IL Core) output** — running locally, so patient data never leaves the customer's network.

## 2. The problem

- HL7 v2 is implemented differently by every vendor and site: the same data in different fields, Z-segments, optional fields used inconsistently, version drift.
- Typical situation: a hospital sends 500 messages, your parser handles 490, the other 10 break. Vendors also change formats without telling anyone.
- HL7's own v2-to-FHIR mappings are a starting point, not a full solution — local variations are left to implementers.
- Existing tools (Caristix, HL7 Soup, HL7 Spy, HAPI TestPanel, iNTERFACEWARE) are mostly **desktop GUIs for viewing and comparing two messages**. They are not built for:
  - scanning a whole corpus and grouping it by variation,
  - running as tests in CI on every code change,
  - checking v2 → FHIR output.

## 3. Who it's for, and why now

| Segment | Why now |
|---|---|
| **Israeli hospitals, HMOs, EHR vendors, integrators** | The Health Data Portability Law (July 2024) mandates FHIR; full compliance by July 2029; MoH funding and a certification program exist. Biggest reported challenges: cost and lack of FHIR knowledge. Their internal feeds are still v2. |
| **Teams leaving Mirth Connect** | Mirth went proprietary from 4.6 (4.5.2 is the last open-source release). Teams moving to BridgeLink, OIE or another engine need proof the output didn't change → regression tests. |
| **Health-tech startups and integration consultants** | Everyone who integrates with hospitals writes v2 parsers and mappings and hits the variation problem. |

## 4. What v1 does (month 1)

| Command | What it does |
|---|---|
| `raphael7 scan <folder>` | Parse every message (tolerant mode), group by structural signature, report clusters, outliers, parse warnings, Z-segments, field-usage stats. Terminal + JSON + static HTML report. |
| `raphael7 diff <a> <b>` | Field-level diff between two messages, or between two clusters. |
| `raphael7 snapshot <msgs>` | Save chosen messages as fixtures with expected parsed values / FHIR output. |
| `raphael7 test` | Run all snapshots (also as a pytest plugin) — fails when parsing or mapping output changes. |
| `raphael7 fhir <msg>` | Convert v2 → FHIR R4 Bundle: ADT → Patient, Encounter; ORU → Observation, DiagnosticReport; ORM → ServiceRequest. |
| `raphael7 validate --profile il-core` | Validate FHIR output against IL Core (wraps the official HL7 FHIR Validator). |

Plus: a **synthetic sample corpus** with deliberate vendor-style variations, for demos and tests. No real PHI ever goes in the repo.

### Out of scope for v1
- Web app / GUI (only a static HTML report)
- MLLP transport, queues, an engine → month 2 candidate
- AI mapping helper → month 2 candidate
- HL7 v3 / CDA, X12, DICOM
- Message types beyond ADT, ORU, ORM

## 5. Technical design

**Stack:** Python 3.12+, `uv` for packaging, Typer (CLI), Rich (terminal output), Pydantic v2 or dataclasses (models), pytest + Hypothesis (tests), Jinja2 (HTML report).

**Parser**
- Reads encoding characters from MSH-1/MSH-2 (don't assume `|^~\&`).
- Handles escape sequences, repetitions, components, subcomponents.
- Accepts `\r`, `\n`, `\r\n` segment terminators; strips MLLP framing; handles batch files (FHS/BHS) and one-message-per-file.
- Two modes: **strict** (raise) and **tolerant** (record warnings, keep going) — tolerant is what makes corpus scanning useful.
- Round-trip property test with Hypothesis: `parse(serialize(m)) == m`.
- Reference structures: check whether hl7apy's (MIT) v2.x structure definitions can be reused as data instead of re-typing the spec.

**Scan / clustering**
- Signature = message type + trigger (MSH-9), version (MSH-12), ordered segment IDs (repeats collapsed), set of populated field positions per segment.
- Exact-signature groups first; then near neighbours (e.g. Jaccard similarity on populated positions) to show "close variants" of the main shape.
- Outlier = small cluster far from the main ones, or messages with parse warnings.
- Streaming + multiprocessing so large logs work.

**v2 → FHIR**
- Follow the HL7 v2-to-FHIR Implementation Guide mappings (segment → resource, data type → data type, table → code system).
- Mappings as plain, testable Python (one module per segment/resource), table-driven where possible.
- Output profile option: base R4 or IL Core.

**Validation**
- Shell out to the official FHIR Validator (`validator_cli.jar`, needs Java) with the `il.core.fhir.r4` package. Optional dependency, clearly documented.

**Performance**
- Benchmark scanning 1M synthetic messages on a laptop; publish numbers in the README; set the target after the first measurement.

**Suggested repo layout**
```
raphael7/
  src/raphael7/
    parser/     # tokenizer, model, escapes, strict/tolerant
    scan/       # signatures, clustering, reports
    diff/
    testing/    # fixtures, snapshots, pytest plugin
    fhir/       # v2 → FHIR mappings per message type
    validate/   # FHIR validator wrapper
    cli.py
  samples/      # synthetic messages only
  tests/
  docs/
```

## 6. Timeline

One month, ~20–30 h/week, Mon Nov 23 – Sun Dec 20, 2026: scan (W1) → diff + tests + ADT (W2) → ORU/ORM + IL Core (W3) → release (W4).
The week-by-week build plan, with exit criteria, is in [ROADMAP.md](ROADMAP.md).

### Month 2 candidates (choose from user feedback, not in advance)
- **Engine-lite:** MLLP listener, ACKs, queue, retries, dead-letter + replay, idempotent writes to a FHIR server.
- **AI mapping helper:** an LLM suggests mappings for Z-segments and local codes; a human approves; approved mappings become tests.
- **Mirth channel analyzer:** read a Mirth channel export, document it, flag what would break when migrating.
- **Drift monitoring:** run `scan` on a schedule and alert when a vendor's format changes.

## 7. License

Apache-2.0 (see [LICENSE](../LICENSE)), chosen on 23 Nov 2026. Hospital and vendor legal teams prefer its explicit patent grant, and it is common in the FHIR ecosystem (e.g. HAPI FHIR).

## 8. Success criteria

- **End of month 1:** published on GitHub + PyPI with tests, benchmarks, docs and a write-up; 3–5 people ran it on their own (test or de-identified) messages; at least one wants to keep using it.

## 9. Risks and how to handle them

| Risk | Mitigation |
|---|---|
| Patient data (PHI) | The tool runs locally; data never leaves the user's network. Repo samples are synthetic. Never accept real patient messages. |
| Basic features already exist elsewhere | Lead with corpus scan + CI tests + FHIR checks, not the viewer or two-message diff. |
| v2 → FHIR long tail | Only ADT, ORU, ORM in v1. |

## 10. References

- HL7 v2-to-FHIR Implementation Guide: https://hl7.org/fhir/uv/v2mappings/
- IL Core (Israel FHIR profiles): https://simplifier.net/ilcore
- FHIR IL community: https://www.fhir-il-community.org
- FHIR Validator releases: https://github.com/hapifhir/org.hl7.fhir.core/releases
- FHIR community chat: https://chat.fhir.org
- hl7apy (possible reference data): https://github.com/crs4/hl7apy
