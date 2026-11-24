# Roadmap — Month 1

Last updated: 23 Nov 2026

**Where we are:** planning done ([project plan](PROJECT_PLAN.md)). Week 1 starts today: repo, parser, sample corpus, `raphael7 scan`.

**Month-1 goal:** ship Raphael7 v1 to GitHub + PyPI and get the first people trying it on their own (test or de-identified) messages.

Rhythm: ~20–30 h/week. Each week ends with a tagged release, so something works even if a later week slips. Outreach runs in parallel and is tracked outside this repo.

Status: ✅ done · 🔄 in progress · ⬜ not started · ⏸ waiting on someone

Who: 🤖 Claude · 👤 Sanja · 🤝 together. Claude builds and Sanja reviews, so a 🤖 task is ticked only after Sanja has reviewed it. 👤 tasks need Sanja's accounts, decisions or HL7 experience.

| # | Dates | Focus | Release | Status |
| --- | --- | --- | --- | --- |
| 1 | Mon Nov 23 – Sun Nov 29 | Parser, sample corpus, `raphael7 scan` | `v0.1` | 🔄 |
| 2 | Mon Nov 30 – Sun Dec 6 | `raphael7 diff`, snapshots, `raphael7 test`, ADT → FHIR | `v0.2` | ⬜ |
| 3 | Mon Dec 7 – Sun Dec 13 | ORU + ORM → FHIR, IL Core validation | `v0.3` | ⬜ |
| 4 | Mon Dec 14 – Sun Dec 20 | HTML report, docs, benchmark, release | `v1.0` | ⬜ |
| — | Mon Dec 21 | Month-1 review, pick month-2 focus | — | ⬜ |

---

## Week 1 — Nov 23 to Nov 29 · `v0.1` 🔄

**Goal:** a tolerant parser and `raphael7 scan` that groups a synthetic corpus by variation and flags outliers.

- [x] 👤 Pick the license: Apache-2.0
- [x] 🤝 Create the public GitHub repo (`sanjahauz/raphael7`)
- [x] 🤖 Repo setup: `uv`, `src/raphael7/` layout ([PROJECT_PLAN §5](PROJECT_PLAN.md#5-technical-design)), Typer CLI stub, pytest, ruff, CI (lint + tests)
- [x] 🤝 Spike (≤ 2 h): can hl7apy's (MIT) v2.x structure definitions be reused as data? 🤖 investigates and recommends, 👤 decides; write the decision down
  - **Decision (23 Nov):** no hl7apy dependency, and no field names in v1. `scan`, `diff` and `test` work on positions (`PID-5`). The parser needs no structure definitions; only reports and a future validator would.
  - **Why:** Sanja's earlier experience with hl7apy: mistakes in its field definitions, and slow. Its code rebuilds each element's structure every time the element is created, with no caching. Its definitions are positional Python tuples, one full copy per version (~16k lines for v2.5), which are hard to check against the spec. Max lengths are missing (`-1` for 2,095 of the 2,120 v2.5 fields), and optionality is only a min/max count.
  - **If we add field names later** (e.g. the week-4 HTML report): build them from the spec, using hl7apy at most as a cross-check, as flat tables per version covering only the segments we use. `fields.tsv` (seg, seq, name, dt, len, opt, rep, table), `datatypes.tsv` (dt, seq, name, dt, len, table) and `messages.txt` in the spec's own notation (`ADT_A01: MSH [{SFT}] EVN PID …`). Load them once into a dict keyed by `("PID", 5)`; the parser never uses them.
- [x] 🤖 Parser
  - [x] Encoding characters from MSH-1/MSH-2 (no hard-coded `|^~\&`)
  - [x] Fields, repetitions, components, subcomponents; escape sequences
  - [x] `\r`, `\n`, `\r\n` terminators; strip MLLP framing; batch files (FHS/BHS) and one message per file
  - [x] Strict mode (raise) and tolerant mode (record warnings, keep going)
  - [x] Serializer + Hypothesis round-trip test: `parse(serialize(m)) == m`
- [x] 🤝 Synthetic sample corpus in `samples/`: ADT, ORU and ORM from 2–3 made-up "vendors", with Z-segments, moved fields, missing segments, odd terminators and a few broken messages. 🤖 generates, 👤 checks that the variations look like real feeds
- [ ] 🤖 `raphael7 scan <folder>`
  - [ ] Signature: MSH-9 type/trigger, MSH-12 version, ordered segment IDs (repeats collapsed), populated field positions
    - **Decision (24 Nov):** a field holding only `""` (HL7 null) counts as populated.
    - **Why:** the spec says `""` means "delete the stored value" and empty means "not sent", but senders use `""` inconsistently. Scan records only that the sender put something there, so a vendor switching between empty and `""` shows up as a variant.
  - [ ] Exact-signature clusters, then near neighbours (Jaccard on populated positions)
  - [ ] Outliers (small, distant clusters + messages with parse warnings), Z-segment list, field-usage stats
  - [ ] Terminal report (Rich) + `--json`
- [ ] 👤 Tag `v0.1`

**Suggested order**

| Day | Work |
| --- | --- |
| Mon | License + GitHub repo 👤; repo setup, CI 🤖; hl7apy spike 🤝 |
| Tue | Tokenizer: encoding chars, fields, components, escapes 🤖 |
| Wed | Terminators, MLLP, batch files; strict/tolerant; round-trip test 🤖 |
| Thu | Synthetic corpus 🤖, realism check 👤 |
| Fri | Signatures + exact clusters 🤖 |
| Sat | Near neighbours, outliers, stats, terminal + JSON output 🤖 |
| Sun | Buffer; review and tag `v0.1` 👤 |

**Exit criteria**
- `raphael7 scan samples/` shows the main clusters, the "vendor" variants as close neighbours, and the broken messages as outliers with warnings
- Round-trip property test passes; CI green

**Watch:** only synthetic data goes in `samples/`, never real patient messages.

---

## Week 2 — Nov 30 to Dec 6 · `v0.2` ⬜

**Goal:** turn chosen messages into regression tests, and produce the first FHIR resources from ADT.

- [ ] 🤖 `raphael7 diff <a> <b>`: field-level diff between two messages, and between two clusters (by signature)
- [ ] 🤖 `raphael7 snapshot <msgs>`: save messages as fixtures with expected parsed values (and FHIR output once mappings exist)
- [ ] 🤖 `raphael7 test` + pytest plugin: fails when parsing or mapping output changes; clear diff on failure; command to accept the new output
- [ ] 🤖 FHIR scaffolding in `src/raphael7/fhir/`: one module per segment/resource, table-driven code mappings, R4 Bundle output
- [ ] 🤝 ADT → Patient (PID) and Encounter (PV1), following the [HL7 v2-to-FHIR IG](https://hl7.org/fhir/uv/v2mappings/). 🤖 implements, 👤 reviews the mapping choices
- [ ] 🤖 `raphael7 fhir <msg>` for ADT
- [ ] 👤 Tag `v0.2`

**Exit criteria**
- Changing a parser or mapping detail makes `raphael7 test` fail with a readable diff
- `raphael7 fhir` turns the sample ADT messages into a Patient + Encounter Bundle

---

## Week 3 — Dec 7 to Dec 13 · `v0.3` ⬜

**Goal:** cover ORU and ORM, and validate output against IL Core.

- [ ] 🤝 ORU → Observation (OBX) + DiagnosticReport (OBR). 🤖 implements, 👤 reviews the mapping choices
- [ ] 🤝 ORM → ServiceRequest (ORC/OBR). 🤖 implements, 👤 reviews the mapping choices
- [ ] 🤖 `--profile base|il-core` output option
- [ ] 🤖 `raphael7 validate --profile il-core`: wrap the official FHIR Validator (`validator_cli.jar`) with the `il.core.fhir.r4` package; optional dependency; clear message when Java is missing
- [ ] 🤖 FHIR snapshot tests for all three message types
- [ ] 👤 Tag `v0.3`

**Exit criteria**
- ADT, ORU and ORM samples convert, and the output passes IL Core validation (or every remaining error is listed as a known gap)

**Watch:**
- The validator needs Java. Keep it optional, so `scan`, `diff` and `test` work without it.
- The v2 → FHIR long tail: only ADT, ORU and ORM ([PROJECT_PLAN §9](PROJECT_PLAN.md#9-risks-and-how-to-handle-them)).

---

## Week 4 — Dec 14 to Dec 20 · `v1.0` ⬜

**Goal:** a polished, installable release.

- [x] 🤖 Check that the name `raphael7` is free on PyPI (free on 23 Nov; `pons` was already taken by another project)
- [ ] 👤 Create the PyPI account and API token; reserve the name early in the week
- [ ] 🤖 Static HTML report for `raphael7 scan` (Jinja2): clusters, outliers, Z-segments, field usage
- [ ] 🤖 Benchmark: scan 1M synthetic messages on a laptop (streaming + multiprocessing); publish the numbers in the README
- [ ] 🤖 README (quick start on the sample corpus), docs for each command
- [ ] 🤝 Demo GIF: 🤖 writes the demo script, 👤 records it
- [ ] 🤝 Publish `v1.0`: 🤖 prepares the release, 👤 publishes; check that `pip install raphael7` / `uvx raphael7` works on a clean machine
- [ ] 🤝 Short write-up: the problem, what Raphael7 does, benchmark numbers. 🤖 drafts, 👤 edits and publishes

**Exit criteria**
- Raphael7 `v1.0` on GitHub + PyPI with README, benchmark and demo GIF
- Installs and runs `raphael7 scan` on the sample corpus on a clean machine

---

## Month-1 review — Mon Dec 21 ⬜

- [ ] 🤝 Check against the success criteria ([PROJECT_PLAN §8](PROJECT_PLAN.md#8-success-criteria))
- [ ] 👤 Pick the month-2 focus from the [candidates](PROJECT_PLAN.md#month-2-candidates-choose-from-user-feedback-not-in-advance) (engine-lite, AI mapping helper, Mirth channel analyzer, drift monitoring), based on user feedback rather than chosen in advance
- [ ] 🤖 Write the month-2 roadmap here
